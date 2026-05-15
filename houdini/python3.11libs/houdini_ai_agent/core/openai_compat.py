"""OpenAI-compatible chat client with streaming, Function Calling, and multi-message support."""

from __future__ import annotations

import base64
import codecs
import json
import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Optional, Union
from urllib import error, request

from houdini_ai_agent.core.codex_cli import send_codex_chat
from houdini_ai_agent.core.config import ProviderConfig, looks_like_direct_key, resolve_api_key


class ProviderCallError(RuntimeError):
    """Raised when a provider call cannot be completed successfully."""


# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    """A single tool call from the model's response."""
    id: str
    function_name: str
    function_arguments: str


@dataclass
class AIResponse:
    """Structured response from the AI model."""
    text: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    reasoning: str = ""
    usage: Dict[str, int] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    def to_text(self) -> str:
        """Return the best text representation (reasoning fallback for empty text)."""
        return self.text or self.reasoning


@dataclass
class StreamChunk:
    """A single chunk from a streaming response."""
    type: str  # "content", "tool_call", "tool_args_delta", "thinking", "done", "error"
    content: str = ""
    tool_call: Optional[ToolCall] = None
    tool_name: str = ""
    tool_args_delta: str = ""
    tool_args_accumulated: str = ""
    tool_index: int = 0
    finish_reason: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    error: str = ""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def build_reasoning_effort(thinking_level: str) -> str:
    mapping = {
        "\u4f4e": "low",
        "\u4e2d": "medium",
        "\u9ad8": "high",
        "\u8d85\u9ad8": "high",
    }
    return mapping.get(thinking_level, "medium")


# ---------------------------------------------------------------------------
# Backward-compatible one-shot chat (non-streaming, returns string)
# ---------------------------------------------------------------------------

def send_chat(
    provider: ProviderConfig,
    system_prompt: str,
    user_text: str,
    image_paths: Optional[Iterable[str]] = None,
    thinking_level: str = "\u4e2d",
    max_tokens: int = 1400,
    timeout_seconds: int = 90,
) -> str:
    """Send a single user message and return the assistant text (backward compatible)."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": _build_user_content(user_text, image_paths or [])},
    ]
    response = send_messages(
        provider=provider,
        messages=messages,
        thinking_level=thinking_level,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
    )
    return response.to_text()


def send_messages(
    provider: ProviderConfig,
    messages: List[Dict[str, object]],
    tools: Optional[List[Dict[str, object]]] = None,
    tool_choice: Optional[Union[str, Dict[str, object]]] = None,
    thinking_level: str = "\u4e2d",
    max_tokens: int = 1400,
    timeout_seconds: int = 90,
) -> AIResponse:
    """Send a multi-message conversation and return a structured AIResponse.

    Supports:
    - Multi-turn conversation with tool results
    - OpenAI Function Calling (tools + tool_choice)
    - Reasoning effort configuration
    """
    api_key = _resolve_key(provider)
    endpoint = _chat_endpoint(provider.base_url)

    payload: Dict[str, object] = {
        "model": provider.model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if provider.supports_reasoning:
        payload["reasoning_effort"] = build_reasoning_effort(thinking_level)
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"

    headers = _build_headers(api_key)
    raw = _post_json(endpoint, payload, headers, timeout_seconds)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderCallError(f"Provider returned invalid JSON: {raw[:280]}") from exc
    return _parse_response(data, raw)


# ---------------------------------------------------------------------------
# Streaming chat (SSE)
# ---------------------------------------------------------------------------

def send_chat_streaming(
    provider: ProviderConfig,
    messages: List[Dict[str, object]],
    tools: Optional[List[Dict[str, object]]] = None,
    tool_choice: Optional[Union[str, Dict[str, object]]] = None,
    thinking_level: str = "\u4e2d",
    max_tokens: int = 1400,
    timeout_seconds: int = 120,
) -> Generator[StreamChunk, None, None]:
    """Stream a chat response using Server-Sent Events (SSE).

    Yields StreamChunk objects for each event:
    - type="content"   → content delta
    - type="thinking"  → reasoning/thinking delta
    - type="tool_args_delta" → partial tool arguments
    - type="tool_call" → complete tool call
    - type="done"      → stream finished
    - type="error"     → error occurred
    """
    api_key = _resolve_key(provider)
    endpoint = _chat_endpoint(provider.base_url)

    payload: Dict[str, object] = {
        "model": provider.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if provider.supports_reasoning:
        payload["reasoning_effort"] = build_reasoning_effort(thinking_level)
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"

    headers = _build_headers(api_key, streaming=True)
    yield from _stream_sse(endpoint, payload, headers, timeout_seconds)


def collect_streaming_response(
    stream: Generator[StreamChunk, None, None],
) -> AIResponse:
    """Collect all chunks from a streaming response into a single AIResponse."""
    text_parts: List[str] = []
    reasoning_parts: List[str] = []
    tool_calls: List[ToolCall] = {}
    finish_reason = "stop"
    usage: Dict[str, int] = {}

    for chunk in stream:
        if chunk.type == "content":
            text_parts.append(chunk.content)
        elif chunk.type == "thinking":
            reasoning_parts.append(chunk.content)
        elif chunk.type == "tool_call":
            if chunk.tool_call:
                tool_calls[chunk.tool_index] = chunk.tool_call
        elif chunk.type == "done":
            finish_reason = chunk.finish_reason or "stop"
            usage = chunk.usage
        elif chunk.type == "error":
            raise ProviderCallError(chunk.error)

    return AIResponse(
        text="".join(text_parts),
        reasoning="".join(reasoning_parts),
        tool_calls=[tool_calls[i] for i in sorted(tool_calls.keys())],
        finish_reason=finish_reason,
        usage=usage,
    )


# ---------------------------------------------------------------------------
# Vision companion (backward compatible)
# ---------------------------------------------------------------------------

def describe_images(
    provider: ProviderConfig,
    user_text: str,
    image_paths: Optional[Iterable[str]] = None,
    response_language: str = "English",
    timeout_seconds: int = 120,
    cwd: Optional[str] = None,
    cancel_event=None,
    process_holder: Optional[dict] = None,
) -> str:
    prompt = (
        "You are the vision companion for a Houdini plugin.\n"
        "Analyze the attached image or images for a downstream text-only agent.\n"
        "Focus on Houdini-relevant information when visible: node graphs, selected nodes, parameter panes, "
        "viewport content, on-screen error text, warnings, UI labels, geometry, and any actionable scene clues.\n"
        "Be concrete and concise.\n"
        f"Return the notes in {response_language}.\n\n"
        f"User intent:\n{user_text or 'Describe the attached image(s) for the downstream agent.'}"
    )
    if provider.source == "codex":
        return send_codex_chat(
            prompt=prompt,
            image_paths=list(image_paths or []),
            model=provider.model,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
            process_holder=process_holder,
        )
    return send_chat(
        provider=provider,
        system_prompt="You are a precise multimodal image analysis assistant.",
        user_text=prompt,
        image_paths=list(image_paths or []),
        thinking_level="\u4e2d",
        max_tokens=900,
        timeout_seconds=timeout_seconds,
    )


# ---------------------------------------------------------------------------
# Message builders for Function Calling conversation
# ---------------------------------------------------------------------------

def build_tool_result_message(
    tool_call_id: str,
    content: str,
    is_error: bool = False,
) -> Dict[str, object]:
    """Build a tool result message for feeding back into the conversation."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content if not is_error else f"[ERROR] {content}",
    }


def build_assistant_tool_call_message(
    text: str,
    tool_calls: List[ToolCall],
) -> Dict[str, object]:
    """Build an assistant message with tool_calls for conversation history."""
    tc_list = []
    for tc in tool_calls:
        tc_list.append({
            "id": tc.id,
            "type": "function",
            "function": {
                "name": tc.function_name,
                "arguments": tc.function_arguments,
            },
        })
    msg: Dict[str, object] = {
        "role": "assistant",
        "content": text,
        "tool_calls": tc_list,
    }
    return msg


def build_tools_schema(
    tool_definitions: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    """Convert tool definitions to OpenAI Function Calling tools format.

    Each tool definition should have: name, description, parameters (JSON Schema).
    Returns the 'tools' array for the API request.
    """
    tools = []
    for tool_def in tool_definitions:
        tools.append({
            "type": "function",
            "function": {
                "name": tool_def.get("name", ""),
                "description": tool_def.get("description", ""),
                "parameters": tool_def.get("parameters", {}),
            },
        })
    return tools


# ---------------------------------------------------------------------------
# Internal: HTTP and SSE
# ---------------------------------------------------------------------------

def _resolve_key(provider: ProviderConfig) -> str:
    api_key = resolve_api_key(provider.api_key_env)
    if not api_key:
        key_hint = (
            "direct key field" if looks_like_direct_key(provider.api_key_env)
            else f"environment variable `{provider.api_key_env}`"
        )
        raise ProviderCallError(
            f"API key is not available from {key_hint}. "
            "Enter a direct key in settings, set the named environment variable before launching Houdini, "
            "or switch the panel back to `Mock Preview`."
        )
    if not provider.base_url.strip():
        raise ProviderCallError("Provider base URL is empty.")
    if not provider.model.strip():
        raise ProviderCallError("Provider model is empty.")
    return api_key


def _build_headers(api_key: str, streaming: bool = False) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "houdini-ai-agent/0.2",
    }
    if streaming:
        headers["Accept"] = "text/event-stream"
    return headers


def _post_json(
    endpoint: str,
    payload: Dict[str, object],
    headers: Dict[str, str],
    timeout_seconds: int,
) -> str:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if "reasoning_effort" in detail and "reasoning_effort" in payload:
            retry_payload = dict(payload)
            retry_payload.pop("reasoning_effort", None)
            return _post_json(endpoint, retry_payload, headers, timeout_seconds)
        raise ProviderCallError(f"HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise ProviderCallError(f"Network error: {exc.reason}") from exc


def _stream_sse(
    endpoint: str,
    payload: Dict[str, object],
    headers: Dict[str, str],
    timeout_seconds: int,
) -> Generator[StreamChunk, None, None]:
    """Send a streaming request and parse SSE events from the response."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(endpoint, data=body, headers=headers, method="POST")

    try:
        response = request.urlopen(req, timeout=timeout_seconds)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        # Retry without reasoning_effort if it caused an error
        if "reasoning_effort" in detail and "reasoning_effort" in payload:
            retry_payload = dict(payload)
            retry_payload.pop("reasoning_effort", None)
            yield from _stream_sse(endpoint, retry_payload, headers, timeout_seconds)
            return
        yield StreamChunk(type="error", error=f"HTTP {exc.code}: {detail}")
        return
    except error.URLError as exc:
        yield StreamChunk(type="error", error=f"Network error: {exc.reason}")
        return

    # Parse SSE with incremental UTF-8 decoding
    tool_calls_buffer: Dict[int, Dict[str, object]] = {}
    pending_usage: Dict[str, int] = {}
    last_finish_reason: Optional[str] = None

    decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
    line_buf = ""

    try:
        while True:
            chunk_bytes = response.read(4096)
            if not chunk_bytes:
                break
            line_buf += decoder.decode(chunk_bytes)

            while "\n" in line_buf:
                line, line_buf = line_buf.split("\n", 1)
                line = line.rstrip("\r")

                if not line.startswith("data: "):
                    continue

                data_str = line[6:]

                if data_str.strip() == "[DONE]":
                    yield StreamChunk(
                        type="done",
                        finish_reason=last_finish_reason or "stop",
                        usage=pending_usage,
                    )
                    return

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                usage_data = data.get("usage")
                if usage_data:
                    pending_usage = _parse_usage(usage_data)

                choices = data.get("choices", [])
                if not choices:
                    continue

                choice = choices[0]
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason")
                if finish_reason:
                    last_finish_reason = finish_reason

                # Reasoning/thinking content
                thinking_text = (
                    delta.get("reasoning_content")
                    or delta.get("thinking_content")
                    or delta.get("reasoning")
                    or ""
                )
                if thinking_text:
                    yield StreamChunk(type="thinking", content=thinking_text)

                # Regular content
                content = delta.get("content")
                if content:
                    yield StreamChunk(type="content", content=content)

                # Tool calls (incremental)
                if delta.get("tool_calls"):
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        tc_id = tc.get("id", "")

                        if tc_id and idx in tool_calls_buffer:
                            existing_id = tool_calls_buffer[idx].get("id", "")
                            if existing_id and existing_id != tc_id:
                                idx = max(tool_calls_buffer.keys()) + 1 if tool_calls_buffer else 0

                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": tc_id,
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }

                        if tc_id:
                            tool_calls_buffer[idx]["id"] = tc_id
                        if "function" in tc:
                            fn = tc["function"]
                            if fn.get("name"):
                                tool_calls_buffer[idx]["function"]["name"] = fn["name"]
                            if "arguments" in fn:
                                tool_calls_buffer[idx]["function"]["arguments"] += fn["arguments"]
                                tname = tool_calls_buffer[idx]["function"].get("name", "")
                                if tname:
                                    yield StreamChunk(
                                        type="tool_args_delta",
                                        tool_index=idx,
                                        tool_name=tname,
                                        tool_args_delta=fn["arguments"],
                                        tool_args_accumulated=tool_calls_buffer[idx]["function"]["arguments"],
                                    )

                # Emit complete tool calls on finish
                if finish_reason and tool_calls_buffer:
                    fixed = _fix_concatenated_tool_args(tool_calls_buffer)
                    tool_calls_buffer = fixed
                    for idx_k in sorted(tool_calls_buffer.keys()):
                        entry = tool_calls_buffer[idx_k]
                        yield StreamChunk(
                            type="tool_call",
                            tool_index=idx_k,
                            tool_call=ToolCall(
                                id=str(entry.get("id", "")),
                                function_name=str(entry["function"]["name"]),
                                function_arguments=str(entry["function"]["arguments"]),
                            ),
                        )
                    tool_calls_buffer = {}

    except Exception as exc:
        yield StreamChunk(type="error", error=str(exc))
    finally:
        try:
            response.close()
        except Exception:
            pass

    # If we reached here without [DONE], emit done anyway
    yield StreamChunk(
        type="done",
        finish_reason=last_finish_reason or "stop",
        usage=pending_usage,
    )


def _fix_concatenated_tool_args(
    buffer: Dict[int, Dict[str, object]],
) -> Dict[int, Dict[str, object]]:
    """Detect and fix proxy-concatenated tool call arguments.

    Some proxies incorrectly concatenate multiple tool call arguments into
    a single entry like {...}{...}. This detects and splits them.
    """
    import uuid as _uuid

    fixed: Dict[int, Dict[str, object]] = {}
    next_idx = max(buffer.keys()) + 1 if buffer else 0

    for idx in sorted(buffer.keys()):
        entry = buffer[idx]
        args_str = str(entry["function"]["arguments"]).strip()

        if not args_str.startswith("{"):
            fixed[idx] = entry
            continue

        try:
            json.loads(args_str)
            fixed[idx] = entry
        except (json.JSONDecodeError, ValueError):
            # Try to split concatenated JSON objects: {...}{...}
            parts = _split_concatenated_json(args_str)
            if len(parts) > 1:
                entry_copy = dict(entry)
                entry_copy["function"] = dict(entry["function"])
                entry_copy["function"]["arguments"] = parts[0]
                fixed[idx] = entry_copy
                for extra_args in parts[1:]:
                    fixed[next_idx] = {
                        "id": f"call_{_uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": entry["function"]["name"],
                            "arguments": extra_args,
                        },
                    }
                    next_idx += 1
            else:
                fixed[idx] = entry

    return fixed


def _split_concatenated_json(text: str) -> List[str]:
    """Split text like '{...}{...}' into individual JSON object strings."""
    parts: List[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                part = text[start : i + 1]
                try:
                    json.loads(part)
                    parts.append(part)
                except (json.JSONDecodeError, ValueError):
                    pass
                start = -1
    return parts


# ---------------------------------------------------------------------------
# Internal: response parsing
# ---------------------------------------------------------------------------

def _parse_response(data: Dict[str, object], raw: str = "") -> AIResponse:
    """Parse a non-streaming API response into an AIResponse."""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        error_info = data.get("error")
        if isinstance(error_info, dict):
            message = error_info.get("message")
            if isinstance(message, str) and message.strip():
                raise ProviderCallError(message.strip())
        snippet = _response_debug_excerpt(data, raw)
        raise ProviderCallError(f"Provider response did not include assistant text. Response excerpt: {snippet}")

    first = choices[0]
    if not isinstance(first, dict):
        raise ProviderCallError(f"Unexpected response format: {raw[:280]}")

    finish_reason = str(first.get("finish_reason", "stop") or "stop")
    message = first.get("message", {})

    if not isinstance(message, dict):
        message = {}

    # Extract text content
    text = _extract_text_from_message(message)

    # Extract reasoning
    reasoning = ""
    for key in ("reasoning_content", "thinking_content", "reasoning"):
        val = message.get(key)
        if isinstance(val, str) and val.strip():
            reasoning = val.strip()
            break

    # Extract tool calls
    tool_calls: List[ToolCall] = []
    raw_tool_calls = message.get("tool_calls")
    if isinstance(raw_tool_calls, list):
        for tc in raw_tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function", {})
            if not isinstance(fn, dict):
                continue
            tool_calls.append(ToolCall(
                id=str(tc.get("id", "")),
                function_name=str(fn.get("name", "")),
                function_arguments=str(fn.get("arguments", "")),
            ))

    # Extract usage
    usage_data = data.get("usage", {})
    usage = _parse_usage(usage_data) if isinstance(usage_data, dict) else {}

    return AIResponse(
        text=text,
        reasoning=reasoning,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        usage=usage,
    )


def _extract_text_from_message(message: Dict[str, object]) -> str:
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
                elif item.get("type") == "text":
                    inner = item.get("content")
                    if isinstance(inner, str) and inner.strip():
                        parts.append(inner.strip())
        if parts:
            return "\n".join(parts)
    return ""


def _parse_usage(usage_data: Dict[str, object]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    if not isinstance(usage_data, dict):
        return result
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"):
        val = usage_data.get(key)
        if isinstance(val, (int, float)):
            result[key] = int(val)
    return result


# ---------------------------------------------------------------------------
# Internal: endpoint and content helpers
# ---------------------------------------------------------------------------

def _chat_endpoint(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _build_user_content(text: str, image_paths: Iterable[str]):
    image_paths = list(image_paths)
    if not image_paths:
        return text or "Please respond to the user."
    content: List[Dict[str, object]] = [
        {"type": "text", "text": text or "Please analyze the attached image(s)."}
    ]
    for image_path in image_paths:
        data_url = _image_to_data_url(Path(image_path))
        if data_url:
            content.append({"type": "image_url", "image_url": {"url": data_url}})
    return content


def _image_to_data_url(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    mime_type, _ = mimetypes.guess_type(str(path))
    mime_type = mime_type or _detect_image_mime(path) or "application/octet-stream"
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:{mime_type};base64,{encoded}"


def _detect_image_mime(path: Path) -> str:
    try:
        header = path.read_bytes()[:16]
    except OSError:
        return ""
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "image/gif"
    if header.startswith(b"BM"):
        return "image/bmp"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    if header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
        return "image/tiff"
    return ""


def _response_debug_excerpt(data: Dict[str, object], raw: str) -> str:
    for key in ("id", "model", "request_id"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            prefix = f"{key}={value.strip()}"
            break
    else:
        prefix = "no-id"
    compact = " ".join((raw or "").split())
    if compact:
        return f"{prefix} | {compact[:280]}"
    try:
        fallback = json.dumps(data, ensure_ascii=False)
    except TypeError:
        fallback = str(data)
    return f"{prefix} | {fallback[:280]}"
