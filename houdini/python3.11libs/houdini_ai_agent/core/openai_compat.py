"""Minimal OpenAI-compatible chat client used by the Houdini panel."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib import error, request

from houdini_ai_agent.core.config import ProviderConfig


class ProviderCallError(RuntimeError):
    """Raised when a provider call cannot be completed successfully."""


def build_reasoning_effort(thinking_level: str) -> str:
    mapping = {
        "低": "low",
        "中": "medium",
        "高": "high",
        "超高": "high",
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
    api_key = os.environ.get(provider.api_key_env, "").strip()
    if not api_key:
        raise ProviderCallError(f"Environment variable `{provider.api_key_env}` is not set.")
    if not provider.base_url.strip():
        raise ProviderCallError("Provider base URL is empty.")
    if not provider.model.strip():
        raise ProviderCallError("Provider model is empty.")

    endpoint = provider.base_url.rstrip("/") + "/chat/completions"
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

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProviderCallError(f"HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise ProviderCallError(f"Network error: {exc.reason}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderCallError(f"Provider returned invalid JSON: {raw[:280]}") from exc
    return _extract_text(data)


def _build_user_content(text: str, image_paths: Iterable[str]) -> List[Dict[str, object]]:
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
    mime_type = mime_type or "application/octet-stream"
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:{mime_type};base64,{encoded}"


def _extract_text(data: Dict[str, object]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
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
                    if parts:
                        return "\n".join(parts)
    error_info = data.get("error")
    if isinstance(error_info, dict):
        message = error_info.get("message")
        if isinstance(message, str) and message.strip():
            raise ProviderCallError(message.strip())
    raise ProviderCallError("Provider response did not include assistant text.")
