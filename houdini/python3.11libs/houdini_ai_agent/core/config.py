"""Provider configuration and external config discovery."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from houdini_ai_agent.core.codex_cli import find_codex_executable, has_codex_auth

try:
    import tomllib
except ImportError:  # pragma: no cover - Houdini 21 uses Python 3.11.
    tomllib = None


APP_CONFIG_DIR = Path.home() / ".houdini_ai_agent"
APP_CONFIG_PATH = APP_CONFIG_DIR / "config.json"
CODEX_MODELS = [
    ("GPT-5.5", "gpt-5.5", "最新前沿模型，能力进一步增强"),
    ("GPT-5.4", "gpt-5.4", "最新前沿模型，能力进一步增强"),
    ("GPT-5.2-Codex", "gpt-5.2-codex", "前沿智能编程模型"),
    ("GPT-5.1-Codex-Max", "gpt-5.1-codex-max", "针对 Codex 优化的模型，深度与快速推理兼备"),
    ("GPT-5.4-Mini", "gpt-5.4-mini", "更轻量的前沿智能编程模型"),
    ("GPT-5.3-Codex", "gpt-5.3-codex", "最新前沿智能编程模型，能力全面增强"),
    ("GPT-5.3-Codex-Spark", "gpt-5.3-codex-spark", "超高速编程模型"),
    ("GPT-5.2", "gpt-5.2", "针对专业工作与长程任务优化"),
    ("GPT-5.1-Codex-Mini", "gpt-5.1-codex-mini", "针对 Codex 优化，更轻量、更快、但性能较弱"),
]


def resolve_api_key(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    env_value = os.environ.get(value, "").strip()
    if env_value:
        return env_value
    return value


def looks_like_direct_key(value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return False
    if os.environ.get(value):
        return False
    return any(marker in value.lower() for marker in ("sk-", "key-", "api_", "bearer ")) or len(value) >= 24


@dataclass
class ProviderConfig:
    name: str
    base_url: str = ""
    api_key_env: str = ""
    model: str = ""
    supports_reasoning: bool = True
    default_thinking_level: str = "中"
    source: str = "custom"

    @property
    def has_key(self) -> bool:
        if self.source == "codex":
            return has_codex_auth()
        return bool(resolve_api_key(self.api_key_env))

    @property
    def status_text(self) -> str:
        if self.source == "mock":
            return "Preview mode"
        if self.source == "codex":
            if not find_codex_executable():
                return "Codex missing"
            return "Signed in" if self.has_key else "Codex login required"
        if not self.api_key_env:
            return "Missing key"
        if looks_like_direct_key(self.api_key_env):
            return "Ready"
        return "Ready" if self.has_key else f"Set {self.api_key_env}"


@dataclass
class ExternalConfigHint:
    source: str
    path: str
    found: bool
    model: str = ""
    provider: str = ""
    note: str = ""


def default_providers() -> List[ProviderConfig]:
    codex_model = _read_codex_default_model()
    return [
        ProviderConfig(
            name="Codex Local",
            base_url="codex://local-cli",
            api_key_env="",
            model=codex_model or "gpt-5.5",
            supports_reasoning=True,
            default_thinking_level="中",
            source="codex",
        ),
        ProviderConfig(
            name="Mock Preview",
            base_url="mock://local-preview",
            api_key_env="",
            model="houdini-ui-preview",
            supports_reasoning=True,
            default_thinking_level="中",
            source="mock",
        )
    ]


def load_app_config(path: Optional[Path] = None) -> Dict[str, Any]:
    config_path = path or APP_CONFIG_PATH
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_app_config(config: Dict[str, Any], path: Optional[Path] = None) -> None:
    config_path = path or APP_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def load_providers() -> List[ProviderConfig]:
    raw = load_app_config()
    providers = default_providers()
    for item in raw.get("providers", []):
        try:
            providers.append(ProviderConfig(**item))
        except TypeError:
            continue
    return providers


def save_providers(providers: List[ProviderConfig]) -> None:
    custom = [asdict(p) for p in providers if p.source != "mock"]
    raw = load_app_config()
    raw["providers"] = custom
    save_app_config(raw)


def discover_external_configs() -> List[ExternalConfigHint]:
    hints: List[ExternalConfigHint] = []
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    codex_path = codex_home / "config.toml"
    hints.append(_read_codex_config(codex_path))

    claude_paths = [
        Path.home() / ".claude" / "settings.json",
        Path.cwd() / ".claude" / "settings.json",
        Path.cwd() / ".claude" / "settings.local.json",
    ]
    for path in claude_paths:
        hints.append(_read_claude_config(path))
    return hints


def _read_codex_config(path: Path) -> ExternalConfigHint:
    if not path.exists():
        return ExternalConfigHint("Codex", str(path), False, note="Not found")
    if tomllib is None:
        return ExternalConfigHint("Codex", str(path), True, note="TOML parser unavailable")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ExternalConfigHint("Codex", str(path), True, note=f"Could not parse: {exc}")

    model = str(data.get("model", "") or data.get("model_name", ""))
    provider = str(data.get("model_provider", "") or data.get("provider", ""))
    return ExternalConfigHint("Codex", str(path), True, model=model, provider=provider, note="Detected")


def _read_claude_config(path: Path) -> ExternalConfigHint:
    if not path.exists():
        return ExternalConfigHint("Claude", str(path), False, note="Not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ExternalConfigHint("Claude", str(path), True, note=f"Could not parse: {exc}")

    model = str(data.get("model", "") or data.get("defaultModel", ""))
    provider = "anthropic" if model else ""
    return ExternalConfigHint("Claude", str(path), True, model=model, provider=provider, note="Detected")


def _read_codex_default_model() -> str:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    path = codex_home / "config.toml"
    if not path.exists() or tomllib is None:
        return ""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(data.get("model", "") or data.get("model_name", ""))
