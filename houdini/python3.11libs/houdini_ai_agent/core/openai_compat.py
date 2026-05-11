"""Minimal OpenAI-compatible chat client used by the Houdini panel."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib import error, request

from houdini_ai_agent.core.codex_cli import send_codex_chat
from houdini_ai_agent.core.config import ProviderConfig, looks_like_direct_key, resolve_api_key


class ProviderCallError(RuntimeError):
    """Raised when a provider call cannot be completed successfully."""


def build_reasoning_effort(thinking_level: str) -> str:
    mapping = {
        "\u4f4e": "low",
        "\u4e2d": "medium",
        "\u9ad8": "high",
        "\u8d85\u9ad8": "high",
    }
    return mapping.get(thinking_level, "medium")


def send_chat(
    provider: ProviderConfig,
    system_prompt: str,
    user_text: str,
    image_paths: Optional[Iterable[str]] = None,
    thinking_level: str = "中",
    max_tokens: int = 1400,
    timeout_seconds: int = 90,
) -> str:
    api_key = resolve_api_key(provider.api_key_env)
    if not api_key:
        key_hint = "direct key field" if looks_like_direct_key(provider.api_key_env) else f"environment variable `{provider.api_key_env}`"
        raise ProviderCallError(
            f"API key is not available from {key_hint}. "
            "Enter a direct key in settings, set the named environment variable before launching Houdini, "
            "or switch the panel back to `Mock Preview`."
        )
    if not provider.base_url.strip():
        raise ProviderCallError("Provider base URL is empty.")
    if not provider.model.strip():
        raise ProviderCallError("Provider model is empty.")

    endpoint = _chat_endpoint(provider.base_url)
    payload = {
        "model": provider.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_user_content(user_text, image_paths or [])},
        ],
        "max_tokens": max_tokens,
    }
    if provider.supports_reasoning:
        payload["reasoning_effort"] = build_reasoning_effort(thinking_level)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "houdini-ai-agent/0.1",
    }

    raw = _post_json(endpoint, payload, headers, timeout_seconds)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderCallError(f"Provider returned invalid JSON: {raw[:280]}") from exc
    return _extract_text(data, raw)


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
            image_paths=image_paths or [],
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
        image_paths=image_paths or [],
        thinking_level="\u4e2d",
        max_tokens=900,
        timeout_seconds=timeout_seconds,
    )


def _post_json(endpoint: str, payload: Dict[str, object], headers: Dict[str, str], timeout_seconds: int) -> str:
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


def _chat_endpoint(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _build_user_content(text: str, image_paths: Iterable[str]):
    image_paths = list(image_paths)
    if not image_paths:
        return text or "Please respond to the user."
    content: List[Dict[str, object]] = [{"type": "text", "text": text or "Please analyze the attached image(s)."}]
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


def _extract_text(data: Dict[str, object], raw: str = "") -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            direct_text = first.get("text")
            if isinstance(direct_text, str) and direct_text.strip():
                return direct_text.strip()
            message = first.get("message")
            if isinstance(message, dict):
                extracted = _extract_text_from_message(message)
                if extracted:
                    return extracted
            delta = first.get("delta")
            if isinstance(delta, dict):
                extracted = _extract_text_from_message(delta)
                if extracted:
                    return extracted
    error_info = data.get("error")
    if isinstance(error_info, dict):
        message = error_info.get("message")
        if isinstance(message, str) and message.strip():
            raise ProviderCallError(message.strip())
    snippet = _response_debug_excerpt(data, raw)
    raise ProviderCallError(f"Provider response did not include assistant text. Response excerpt: {snippet}")


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

    reasoning = message.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning.strip()

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        parts = []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function")
            if isinstance(function, dict):
                name = str(function.get("name", "") or "").strip()
                arguments = function.get("arguments")
                if isinstance(arguments, str) and arguments.strip():
                    parts.append(arguments.strip())
                elif name:
                    parts.append(name)
        if parts:
            return "\n".join(parts)
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
