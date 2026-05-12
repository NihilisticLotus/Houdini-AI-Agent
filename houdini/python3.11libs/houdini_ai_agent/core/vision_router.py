"""Provider selection for direct image input and companion vision backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from houdini_ai_agent.core.config import (
    ProviderConfig,
    VisionBackendConfig,
    provider_is_codex_local,
    provider_model_allows_vision,
)


@dataclass(frozen=True)
class VisionBackendResolution:
    provider: Optional[ProviderConfig]
    mode: str
    status: str = ""


def provider_can_read_images(provider: ProviderConfig) -> bool:
    return provider_model_allows_vision(provider)


class VisionRouter:
    """Resolve the provider that should receive image input for a request."""

    def __init__(self, providers: Iterable[ProviderConfig], config: VisionBackendConfig):
        self.providers = list(providers)
        self.config = config

    def resolve(self, primary: ProviderConfig) -> VisionBackendResolution:
        if provider_can_read_images(primary):
            return VisionBackendResolution(primary, "direct")

        mode = self.config.normalized_mode()
        if mode == "disabled":
            return VisionBackendResolution(None, mode)
        if mode == "codex":
            return self._resolve_codex(primary, mode)
        if mode == "provider":
            return self._resolve_named_provider(mode)
        if mode == "mcp":
            return VisionBackendResolution(
                None,
                mode,
                "An MCP vision backend is configured, but this plugin build does not execute MCP vision backends yet.",
            )
        if mode == "skill":
            return VisionBackendResolution(
                None,
                mode,
                "A skill vision backend is configured, but this plugin build does not execute skill vision backends yet.",
            )
        return self._resolve_auto(primary, mode)

    def _resolve_codex(self, primary: ProviderConfig, mode: str) -> VisionBackendResolution:
        provider = self._provider_by_source("codex")
        if provider is None:
            return VisionBackendResolution(
                None,
                mode,
                "Codex Local is selected as the vision backend, but it is not configured on this machine.",
            )
        if provider.name == primary.name:
            return VisionBackendResolution(provider, mode)
        if not self._provider_ready_for_vision(provider):
            return VisionBackendResolution(
                None,
                mode,
                "Codex Local is selected as the vision backend, but it is not ready to read images.",
            )
        return VisionBackendResolution(provider, mode)

    def _resolve_named_provider(self, mode: str) -> VisionBackendResolution:
        target = self.config.target.strip()
        provider = self._provider_by_name(target) if target else None
        if provider is None:
            return VisionBackendResolution(
                None,
                mode,
                "A specific vision provider is selected, but no provider name is configured.",
            )
        if not self._provider_ready_for_vision(provider):
            return VisionBackendResolution(
                None,
                mode,
                f"{provider.name} is selected as the vision backend, but it is not ready to read images.",
            )
        return VisionBackendResolution(provider, mode)

    def _resolve_auto(self, primary: ProviderConfig, mode: str) -> VisionBackendResolution:
        explicit_candidates = []
        fallback_candidates = []
        for provider in self.providers:
            if provider.name == primary.name:
                continue
            if provider_is_codex_local(provider):
                continue
            if not self._provider_ready_for_vision(provider):
                continue
            if provider.use_as_vision_fallback:
                explicit_candidates.append(provider)
            else:
                fallback_candidates.append(provider)

        if explicit_candidates:
            return VisionBackendResolution(explicit_candidates[0], mode)
        if fallback_candidates:
            return VisionBackendResolution(fallback_candidates[0], mode)
        return VisionBackendResolution(
            None,
            mode,
            "自动模式没有找到可用的非 Codex 视觉后端。当前主模型不是 Codex Local，因此不会隐式调用 Codex；请切换到 Codex Local、勾选一个支持视觉的 provider，或在视觉后端里显式选择 Codex Local。",
        )

    def _provider_by_name(self, name: str) -> Optional[ProviderConfig]:
        for provider in self.providers:
            if provider.name == name:
                return provider
        return None

    def _provider_by_source(self, source: str) -> Optional[ProviderConfig]:
        for provider in self.providers:
            if provider.source == source:
                return provider
        return None

    def _provider_ready_for_vision(self, provider: ProviderConfig) -> bool:
        if provider.source == "mock":
            return False
        if not provider_can_read_images(provider):
            return False
        if provider.source != "codex" and (not provider.base_url.strip() or not provider.model.strip()):
            return False
        return provider.has_key

