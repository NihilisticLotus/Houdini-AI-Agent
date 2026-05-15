"""Context manager for the Houdini AI Agent.

Handles token estimation, context trimming, image stripping, and tool result
compression. Designed to work with the AgentLoop and Session layers.

Design principles (inspired by first-principles analysis):
1. **Never truncate user/assistant text** — only compress tool results
2. **Round-based grouping** — user messages as round boundaries
3. **Layered compression** — stale marking → image stripping → tiered tool
   compression → round trimming, progressively more aggressive
4. **Heuristic token estimation** — no external dependencies; hot path uses
   fast char-based heuristics
5. **Proactive + reactive** — trim before API call (proactive) and after
   context_length_exceeded error (reactive)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Image tokens: base64 encoded images are very expensive; rough estimate
_IMAGE_URL_TOKENS = 765

# Message overhead tokens (role, separators, etc.)
_MESSAGE_OVERHEAD = 4

# Tool call overhead tokens per call
_TOOL_CALL_OVERHEAD = 8

# Tool definition overhead tokens per tool
_TOOL_DEF_OVERHEAD = 30

# Default context limit for most modern models
DEFAULT_CONTEXT_LIMIT = 128_000

# Proactive compression threshold (fraction of context limit)
PROACTIVE_THRESHOLD = 0.85

# Tools whose results should NEVER be compressed (errors are critical feedback)
_NEVER_COMPRESS_TOOLS = frozenset({"check_errors"})

# Tools with built-in pagination — don't compress
_SELF_PAGINATING_TOOLS = frozenset({
    "get_houdini_node_doc", "execute_python",
})

# Query tools — results benefit from line-based pagination
_QUERY_TOOLS = frozenset({
    "get_network_structure", "get_node_parameters", "list_children",
    "check_errors", "get_node_positions", "find_nodes_by_param",
})

# Operation tools — results benefit from node path extraction
_OP_TOOLS = frozenset({
    "create_node", "delete_node", "connect_nodes", "copy_node",
    "batch_set_parameters", "set_display_flag", "layout_nodes",
    "set_node_parameter",
})


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_tokens_for_text(text: str) -> int:
    """Estimate token count for a text string using heuristic rules.

    Uses different ratios for CJK vs ASCII characters:
    - CJK characters: ~1.5 chars/token
    - Code punctuation ({}[]:,;()=<>): 1 char/token
    - Other ASCII: ~3.8 chars/token
    """
    if not text:
        return 0

    cjk_count = 0
    code_punct = 0
    other_count = 0

    for ch in text:
        cp = ord(ch)
        # CJK Unified Ideographs + CJK Extension blocks
        if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
                0x20000 <= cp <= 0x2A6DF):
            cjk_count += 1
        elif ch in "{}[]:,;()=<>":
            code_punct += 1
        else:
            other_count += 1

    # Heuristic ratios from reference project
    cjk_tokens = cjk_count / 1.5 if cjk_count else 0
    other_tokens = other_count / 3.8 if other_count else 0
    return int(cjk_tokens + code_punct + other_tokens) + 1


def estimate_tokens_for_messages(
    messages: List[Dict[str, object]],
    tools: Optional[List[Dict[str, object]]] = None,
) -> int:
    """Estimate total token count for a message list + optional tool definitions.

    Uses fast heuristic estimation suitable for hot-path use in agent loops.
    """
    total = 0

    # Tool definitions overhead
    if tools:
        for tool_def in tools:
            total += _TOOL_DEF_OVERHEAD
            func = tool_def.get("function", {}) if isinstance(tool_def, dict) else {}
            desc = str(func.get("description", ""))
            params_str = json.dumps(func.get("parameters", {}), ensure_ascii=False)
            total += len(desc) // 4
            total += len(params_str) // 4

    for msg in messages:
        total += _MESSAGE_OVERHEAD
        content = msg.get("content")
        if isinstance(content, str):
            total += len(content) // 3
        elif isinstance(content, list):
            # Multimodal content (text + image_url parts)
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    total += len(str(part.get("text", ""))) // 3
                elif part.get("type") == "image_url":
                    total += _IMAGE_URL_TOKENS

        # Tool calls in assistant messages
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                total += _TOOL_CALL_OVERHEAD
                if isinstance(tc, dict):
                    fn = tc.get("function", {})
                    if isinstance(fn, dict):
                        total += len(str(fn.get("name", ""))) // 4
                        total += len(str(fn.get("arguments", ""))) // 4

        # Tool result message
        if msg.get("role") == "tool":
            result_content = str(msg.get("content", ""))
            total += len(result_content) // 3

    return total


# ---------------------------------------------------------------------------
# Image stripping
# ---------------------------------------------------------------------------

def strip_images(
    messages: List[Dict[str, object]],
    keep_recent_user: int = 2,
) -> int:
    """Strip image_url content from messages, keeping recent user images.

    Args:
        messages: Message list (modified in-place).
        keep_recent_user: Number of most recent user messages whose images
            to preserve. 0 = strip all images.

    Returns:
        Number of images stripped.
    """
    if not messages:
        return 0

    # Find indices of the N most recent user messages to protect
    protected = set()
    if keep_recent_user > 0:
        user_indices = [i for i, m in enumerate(messages)
                        if isinstance(m, dict) and m.get("role") == "user"]
        for idx in user_indices[-keep_recent_user:]:
            protected.add(idx)

    stripped = 0
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        if i in protected:
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue

        # Extract only text parts
        text_parts = []
        has_images = False
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                text = part.get("text", "")
                if text:
                    text_parts.append(text)
            elif part.get("type") == "image_url":
                has_images = True
                stripped += 1

        if has_images:
            text = "\n".join(text_parts)
            if not text.strip():
                text = "[图片已移除以节省上下文空间]"
            msg["content"] = text

    return stripped


# ---------------------------------------------------------------------------
# Tool result compression
# ---------------------------------------------------------------------------

def compress_tool_result(
    tool_name: str,
    content: str,
    max_length: int = 300,
) -> str:
    """Compress a tool result based on tool type.

    Different tools have different compression strategies:
    - check_errors: never compress
    - get_network_structure: keep node names/connections, strip positions
    - get_node_parameters: keep modified params, collapse defaults
    - query tools: line-based pagination
    - op tools: extract node paths
    - others: smart summary
    """
    if not content:
        return content

    # Never compress critical tools
    if tool_name in _NEVER_COMPRESS_TOOLS:
        return content

    # Self-paginating tools
    if tool_name in _SELF_PAGINATING_TOOLS:
        return content

    # If already short enough, return as-is
    if len(content) <= max_length:
        return content

    # Tool-specific strategies
    if tool_name == "get_network_structure":
        return _compress_network_structure(content, max_length)
    elif tool_name == "get_node_parameters":
        return _compress_node_parameters(content, max_length)
    elif tool_name in _QUERY_TOOLS:
        return _paginate_lines(content, max_lines=50)
    elif tool_name in _OP_TOOLS:
        return _compress_op_result(content, max_length)
    else:
        return _smart_summary(content, max_length)


def _compress_network_structure(content: str, max_len: int) -> str:
    """Keep node names, types, connections; strip position coordinates."""
    lines = content.split("\n")
    kept = []
    for line in lines:
        # Strip position patterns like (x.xxx, y.xxx)
        cleaned = re.sub(r'\([-+]?\d+\.?\d*,\s*[-+]?\d+\.?\d*\)', '', line)
        # Strip flags display like [D][R][B]
        cleaned = re.sub(r'\[[DRB]\]', '', cleaned)
        cleaned = cleaned.strip()
        if cleaned:
            kept.append(cleaned)
    result = "\n".join(kept)
    if len(result) > max_len:
        result = result[:max_len - 20] + "\n...[truncated]"
    return result


def _compress_node_parameters(content: str, max_len: int) -> str:
    """Keep non-default/modified parameters, collapse defaults."""
    lines = content.split("\n")
    kept = []
    for line in lines:
        # Skip lines that are just default values
        if "[default]" in line.lower():
            continue
        # Skip empty separator lines
        if not line.strip():
            continue
        kept.append(line.rstrip())
    result = "\n".join(kept)
    if not result.strip():
        # All were defaults — return a summary
        return content[:max_len]
    if len(result) > max_len:
        result = result[:max_len - 20] + "\n...[truncated]"
    return result


def _paginate_lines(content: str, max_lines: int = 50) -> str:
    """Paginate content by lines, truncating excess."""
    lines = content.split("\n")
    if len(lines) <= max_lines:
        return content
    kept = lines[:max_lines]
    return "\n".join(kept) + f"\n...[{len(lines) - max_lines} more lines]"


def _compress_op_result(content: str, max_len: int) -> str:
    """Extract node paths from operation results."""
    # Extract node paths like /obj/geo1/box1
    paths = re.findall(r'/[\w/\d]+', content)
    unique_paths = []
    seen = set()
    for p in paths[:10]:
        if p not in seen:
            seen.add(p)
            unique_paths.append(p)

    if unique_paths:
        result = "Affected: " + ", ".join(unique_paths[:5])
        if len(result) > max_len:
            result = result[:max_len - 10] + "..."
        return result
    return content[:max_len]


def _smart_summary(content: str, max_len: int) -> str:
    """Smart summary: extract key info rather than simple truncation."""
    # 1. Extract node paths
    paths = re.findall(r'/[\w/\d]+', content)
    if paths:
        unique = list(dict.fromkeys(paths))[:5]
        summary = "Nodes: " + ", ".join(unique)
        remaining = max_len - len(summary) - 10
        if remaining > 50:
            summary += "\n" + content[:remaining]
        return summary[:max_len]

    # 2. Extract numbers/stats
    stats = re.findall(r'(\d+)\s*(?:个|nodes?|points?|prims?|polygons?|个节点)', content)
    if stats:
        stat_str = ", ".join(f"n={s}" for s in stats[:5])
        return f"[Stats: {stat_str}] {content[:max_len - len(stat_str) - 15]}"

    # 3. Detect errors
    if any(kw in content.lower() for kw in ("error", "错误", "warning", "警告", "failed", "失败")):
        # Keep more for error messages
        return content[:max(500, max_len)]

    # 4. First line fallback
    first_line = content.split("\n")[0]
    if len(first_line) <= max_len:
        return first_line
    return first_line[:max_len]


# ---------------------------------------------------------------------------
# Round-based context trimming
# ---------------------------------------------------------------------------

@dataclass
class _Round:
    """A conversation round: starts with a user message, includes subsequent
    assistant/tool/system messages until the next user message."""
    messages: List[Dict[str, object]] = field(default_factory=list)


def _split_into_rounds(messages: List[Dict[str, object]]) -> List[_Round]:
    """Split messages into rounds, where each round starts with a user message."""
    rounds: List[_Round] = []
    current = _Round()

    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user" and current.messages:
            rounds.append(current)
            current = _Round()
        current.messages.append(msg)

    if current.messages:
        rounds.append(current)

    return rounds


def trim_context(
    messages: List[Dict[str, object]],
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
    trim_level: int = 1,
    supports_vision: bool = True,
) -> List[Dict[str, object]]:
    """Progressively trim context to fit within token budget.

    Cursor-style core principles:
    - **Never truncate user message text**
    - **Never truncate assistant message text**
    - Only compress tool results (role='tool')
    - Trim by rounds (oldest first)

    Args:
        messages: Conversation messages.
        context_limit: Maximum context token budget.
        trim_level: Aggressiveness level (1=light, 2=medium, 3+=heavy).
        supports_vision: Whether the model supports image input.

    Returns:
        Trimmed message list.
    """
    if not messages:
        return messages

    # Deep-copy message dicts to avoid mutating the original history
    messages = [dict(m) if isinstance(m, dict) else m for m in messages]

    # Step 0: Strip images based on trim level
    if not supports_vision or trim_level >= 3:
        strip_images(messages, keep_recent_user=0)
    elif trim_level == 2:
        strip_images(messages, keep_recent_user=1)
    else:
        strip_images(messages, keep_recent_user=2)

    # Split into system prefix + rounds
    system_prefix: List[Dict[str, object]] = []
    body_start = 0
    for i, msg in enumerate(messages):
        if isinstance(msg, dict) and msg.get("role") == "system":
            system_prefix.append(msg)
            body_start = i + 1
        else:
            break

    body = messages[body_start:]
    if not body:
        return messages

    rounds = _split_into_rounds(body)

    # Determine how many rounds to keep and tool compression strategy
    if trim_level <= 1:
        # Light: keep 70% of rounds, compress old tool results to 300 chars
        keep_count = max(3, int(len(rounds) * 0.7))
        tool_max = 300
        compress_old_pct = 0.3  # Compress oldest 30%
    elif trim_level == 2:
        # Medium: keep 3 rounds, compress to 150 chars
        keep_count = 3
        tool_max = 150
        compress_old_pct = 0.5
    else:
        # Heavy: keep 2 rounds, compress to 100 chars
        keep_count = 2
        tool_max = 100
        compress_old_pct = 1.0

    # Compress tool results in old rounds
    n_rounds = len(rounds)
    old_threshold = n_rounds - keep_count

    for r_idx, rnd in enumerate(rounds):
        if r_idx >= old_threshold:
            continue  # Protected recent rounds
        fraction = (old_threshold - r_idx) / max(old_threshold, 1)
        if fraction > compress_old_pct:
            continue

        for msg in rnd.messages:
            if not isinstance(msg, dict):
                continue
            if msg.get("role") != "tool":
                continue
            content = str(msg.get("content", ""))
            if len(content) > tool_max:
                msg["content"] = _smart_summary(content, tool_max)

    # Trim oldest rounds
    if len(rounds) > keep_count:
        rounds = rounds[-keep_count:]

    # Reassemble
    result = list(system_prefix)

    # Add a system message noting the trim
    history_note = f"（级别 {trim_level}，已保留最近 {keep_count} 轮对话）"
    result.append({
        "role": "system",
        "content": (
            f"[上下文管理] 已自动裁剪历史{history_note}。"
            f"请继续完成当前任务。不要提及此裁剪。"
        ),
    })

    for rnd in rounds:
        result.extend(rnd.messages)

    return result


# ---------------------------------------------------------------------------
# Proactive compression (for agent loop)
# ---------------------------------------------------------------------------

def smart_compress(
    messages: List[Dict[str, object]],
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
    supports_vision: bool = True,
    tools: Optional[List[Dict[str, object]]] = None,
) -> List[Dict[str, object]]:
    """Proactive context compression for agent loop.

    Called at the start of each agent loop iteration when estimated tokens
    exceed 85% of the context limit. Uses layered approach:

    1. Mark stale tool results
    2. Strip old images (keep 2 most recent user messages)
    3. Tiered tool result compression for old rounds
    4. Trim oldest rounds if still over budget

    Args:
        messages: Conversation messages (modified in-place where possible).
        context_limit: Maximum context token budget.
        supports_vision: Whether the model supports image input.
        tools: Tool definitions (included in token estimation).

    Returns:
        Compressed message list.
    """
    if not messages:
        return messages

    # Deep-copy message dicts to avoid mutating the original history
    messages = [dict(m) if isinstance(m, dict) else m for m in messages]

    current_tokens = estimate_tokens_for_messages(messages, tools)
    target = int(context_limit * 0.75)  # Compress to 75% to leave room

    if current_tokens <= context_limit * PROACTIVE_THRESHOLD:
        return messages

    # Step 1: Mark stale tool results
    _mark_stale_results(messages)

    current_tokens = estimate_tokens_for_messages(messages, tools)
    if current_tokens <= target:
        return messages

    # Step 2: Strip old images
    strip_images(messages, keep_recent_user=2)

    current_tokens = estimate_tokens_for_messages(messages, tools)
    if current_tokens <= target:
        return messages

    # Step 3: Split into rounds and compress old tool results
    system_prefix, rounds = _split_with_system(messages)

    # Protect most recent 50% of rounds
    n_rounds = len(rounds)
    protect_from = n_rounds // 2

    # Build tool_call_id → tool_name mapping for targeted compression
    tc_id_to_name = _build_tc_id_map(rounds)

    for r_idx, rnd in enumerate(rounds):
        if r_idx >= protect_from:
            continue
        for msg in rnd.messages:
            if not isinstance(msg, dict) or msg.get("role") != "tool":
                continue
            content = str(msg.get("content", ""))
            tc_id = str(msg.get("tool_call_id", ""))
            tool_name = tc_id_to_name.get(tc_id, "")
            if len(content) > 200:
                msg["content"] = compress_tool_result(tool_name, content, max_length=200)

    # Reassemble and check
    result = system_prefix + [m for rnd in rounds for m in rnd.messages]
    current_tokens = estimate_tokens_for_messages(result, tools)
    if current_tokens <= target:
        return result

    # Step 4: Trim oldest rounds progressively
    while len(rounds) > 2 and current_tokens > target:
        rounds = rounds[1:]  # Drop oldest round
        result = system_prefix + [m for rnd in rounds for m in rnd.messages]
        current_tokens = estimate_tokens_for_messages(result, tools)

    # Add compression notice
    result.append({
        "role": "system",
        "content": "[上下文管理] 已压缩历史以适配上下文窗口。请继续完成当前任务。",
    })

    return result


def _mark_stale_results(messages: List[Dict[str, object]]) -> None:
    """Mark stale tool results: when the same query tool is called with the
    same args multiple times, older results are replaced by newer ones."""
    # Track (tool_name, args_key) → latest message index
    latest_call: Dict[str, int] = {}
    tc_id_to_name = _build_tc_id_map_simple(messages)

    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "tool":
            continue
        tc_id = str(msg.get("tool_call_id", ""))
        tool_name = tc_id_to_name.get(tc_id, "")
        if tool_name in _QUERY_TOOLS:
            key = f"{tool_name}:{tc_id}"
            if key in latest_call:
                # Mark older result as stale
                old_idx = latest_call[key]
                old_msg = messages[old_idx]
                if isinstance(old_msg, dict):
                    old_content = str(old_msg.get("content", ""))
                    if "[Stale]" not in old_content:
                        old_msg["content"] = (
                            f"[Stale] 此 {tool_name} 结果已被后续查询更新。"
                        )
            latest_call[key] = i


def _split_with_system(
    messages: List[Dict[str, object]],
) -> Tuple[List[Dict[str, object]], List[_Round]]:
    """Split messages into system prefix + rounds."""
    system_prefix: List[Dict[str, object]] = []
    body_start = 0
    for i, msg in enumerate(messages):
        if isinstance(msg, dict) and msg.get("role") == "system":
            system_prefix.append(msg)
            body_start = i + 1
        else:
            break
    body = messages[body_start:]
    rounds = _split_into_rounds(body)
    return system_prefix, rounds


def _build_tc_id_map(rounds: List[_Round]) -> Dict[str, str]:
    """Build tool_call_id → tool_name mapping from rounds."""
    mapping: Dict[str, str] = {}
    for rnd in rounds:
        for msg in rnd.messages:
            if not isinstance(msg, dict):
                continue
            if msg.get("role") == "assistant":
                tool_calls = msg.get("tool_calls")
                if isinstance(tool_calls, list):
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            tc_id = str(tc.get("id", ""))
                            fn = tc.get("function", {})
                            if isinstance(fn, dict):
                                mapping[tc_id] = str(fn.get("name", ""))
    return mapping


def _build_tc_id_map_simple(messages: List[Dict[str, object]]) -> Dict[str, str]:
    """Build tool_call_id → tool_name mapping from flat message list."""
    mapping: Dict[str, str] = {}
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "assistant":
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tc_id = str(tc.get("id", ""))
                        fn = tc.get("function", {})
                        if isinstance(fn, dict):
                            mapping[tc_id] = str(fn.get("name", ""))
    return mapping


# ---------------------------------------------------------------------------
# Error detection helpers
# ---------------------------------------------------------------------------

_CONTEXT_EXCEEDED_KEYWORDS = (
    "context_length_exceeded",
    "maximum context length",
    "token limit",
    "too many tokens",
    "request too large",
    "payload too large",
    "context window",
    "input too long",
)


def is_context_exceeded_error(error_text: str) -> bool:
    """Check if an error message indicates context length was exceeded."""
    lowered = error_text.lower()
    return any(kw in lowered for kw in _CONTEXT_EXCEEDED_KEYWORDS)


def is_server_transient_error(error_text: str) -> bool:
    """Check if an error message indicates a transient server error."""
    lowered = error_text.lower()
    return any(kw in lowered for kw in (
        "500", "502", "503", "504",
        "internal server error",
        "server error",
        "overloaded",
        "rate limit",
        "too many requests",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
    ))


# ---------------------------------------------------------------------------
# Result compression for agent loop feedback
# ---------------------------------------------------------------------------

def compress_result_for_context(
    result: Dict[str, object],
    max_length: int = 2000,
) -> str:
    """Compress a tool result dict for feeding back into conversation context.

    This is used by the agent loop when writing tool result messages.
    """
    text = json.dumps(result, ensure_ascii=False)
    if len(text) <= max_length:
        return text
    # Keep head + tail
    head = text[:1500]
    tail = text[-500:]
    return f"{head}\n...[truncated]...\n{tail}"
