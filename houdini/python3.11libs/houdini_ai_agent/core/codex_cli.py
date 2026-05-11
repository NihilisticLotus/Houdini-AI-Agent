"""Local Codex CLI bridge for Houdini AI Agent."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
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
    cmd.append("-")
    for image_path in image_paths or []:
        prepared = _prepare_image_for_cli(Path(image_path))
        cmd.extend(["--image", str(prepared)])

    process = subprocess.Popen(
        cmd,
        cwd=cwd or str(Path.home()),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process_holder is not None:
        process_holder["process"] = process
    try:
        stdout, stderr = process.communicate(input=prompt, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_process(process)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except Exception:
            stdout, stderr = "", ""
        raise CodexCallError(f"Codex CLI timed out after {timeout_seconds} seconds.") from exc
    finally:
        if process_holder is not None:
            process_holder.pop("process", None)

    if cancel_event is not None and cancel_event.is_set():
        raise CodexCallError("Codex request was stopped.")
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


def _prepare_image_for_cli(path: Path) -> Path:
    if not path.exists() or not path.is_file():
        raise CodexCallError(f"Image attachment does not exist: {path}")
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
        return path
    suffix = _detect_image_suffix(path)
    if not suffix:
        raise CodexCallError(f"Image attachment has an unknown image format: {path}")
    cache_dir = Path(tempfile.gettempdir()) / "houdini_ai_agent_codex_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{path.stem or 'image'}_{abs(hash(str(path)))}{suffix}"
    try:
        if not target.exists() or target.stat().st_mtime < path.stat().st_mtime:
            shutil.copy2(str(path), str(target))
    except OSError as exc:
        raise CodexCallError(f"Could not prepare image attachment for Codex: {path}") from exc
    return target


def _detect_image_suffix(path: Path) -> str:
    try:
        header = path.read_bytes()[:16]
    except OSError:
        return ""
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return ".gif"
    if header.startswith(b"BM"):
        return ".bmp"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return ".webp"
    if header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
        return ".tiff"
    return ""
