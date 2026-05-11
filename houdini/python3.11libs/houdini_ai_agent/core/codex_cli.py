"""Local Codex CLI bridge for Houdini AI Agent."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Iterable, Optional


class CodexCallError(RuntimeError):
    """Raised when the local Codex CLI call fails."""


def find_codex_executable() -> Optional[str]:
    explicit = os.environ.get("CODEX_CLI_PATH", "").strip()
    if explicit and Path(explicit).exists():
        return explicit
    discovered = shutil.which("codex")
    if discovered:
        return discovered
    fallback = Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin" / "codex.exe"
    if fallback.exists():
        return str(fallback)
    return None


def has_codex_auth() -> bool:
    auth_path = Path.home() / ".codex" / "auth.json"
    return auth_path.exists()


def send_codex_chat(
    prompt: str,
    image_paths: Optional[Iterable[str]] = None,
    model: str = "",
    cwd: Optional[str] = None,
    timeout_seconds: int = 180,
    cancel_event=None,
    process_holder: Optional[dict] = None,
) -> str:
    codex_exe = find_codex_executable()
    if not codex_exe:
        raise CodexCallError("Codex CLI executable was not found on this machine.")
    if not has_codex_auth():
        raise CodexCallError("Codex local login was not found. Please sign in to Codex first.")

    output_dir = Path(tempfile.gettempdir()) / "houdini_ai_agent_codex"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "last_message.txt"
    if output_file.exists():
        try:
            output_file.unlink()
        except OSError:
            pass

    cmd = [
        codex_exe,
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--output-last-message",
        str(output_file),
    ]
    if model.strip():
        cmd.extend(["-m", model.strip()])
    for image_path in image_paths or []:
        if Path(image_path).exists():
            cmd.extend(["--image", str(image_path)])
    cmd.append(prompt)

    process = subprocess.Popen(
        cmd,
        cwd=cwd or str(Path.home()),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process_holder is not None:
        process_holder["process"] = process
    started = time.monotonic()
    while process.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            _terminate_process(process)
            raise CodexCallError("Codex request was stopped.")
        if time.monotonic() - started > timeout_seconds:
            _terminate_process(process)
            raise CodexCallError(f"Codex CLI timed out after {timeout_seconds} seconds.")
        time.sleep(0.1)
    stdout, stderr = process.communicate()
    if process_holder is not None:
        process_holder.pop("process", None)
    if process.returncode != 0:
        detail = (stderr or stdout or "").strip()
        raise CodexCallError(detail or f"Codex CLI exited with code {process.returncode}.")

    if output_file.exists():
        content = output_file.read_text(encoding="utf-8", errors="replace").strip()
        if content:
            return content
    stdout = (stdout or "").strip()
    if stdout:
        return stdout
    raise CodexCallError("Codex CLI completed without returning assistant text.")


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=3)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
