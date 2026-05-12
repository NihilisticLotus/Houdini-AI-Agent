from __future__ import annotations

import unittest

from houdini_ai_agent.core.config import ProviderConfig, VisionBackendConfig
from houdini_ai_agent.core.vision_router import VisionRouter, provider_can_read_images


def custom_provider(
    name: str,
    model: str,
    *,
    vision: bool = False,
    fallback: bool = False,
    key: str = "sk-test-000000000000000000000000",
) -> ProviderConfig:
    return ProviderConfig(
        name=name,
        base_url="https://example.test/v1",
        api_key_env=key,
        model=model,
        supports_vision=vision,
        use_as_vision_fallback=fallback,
        source="custom",
    )


class VisionRouterTests(unittest.TestCase):
    def test_primary_vision_provider_reads_images_directly(self):
        primary = custom_provider("Vision GPT", "gpt-5.5", vision=True)
        result = VisionRouter([primary], VisionBackendConfig(mode="auto")).resolve(primary)

        self.assertEqual("direct", result.mode)
        self.assertIs(primary, result.provider)

    def test_known_text_only_model_ignores_stale_vision_flag(self):
        provider = custom_provider("GLM", "glm-5.1", vision=True)

        self.assertFalse(provider_can_read_images(provider))

    def test_auto_uses_non_codex_vision_companion_for_text_primary(self):
        primary = custom_provider("GLM", "glm-5.1", vision=False)
        codex = ProviderConfig(
            name="Codex Local",
            base_url="codex://local-cli",
            model="gpt-5.5",
            supports_vision=True,
            source="codex",
        )
        companion = custom_provider("Vision Companion", "gpt-5.5", vision=True, fallback=True)

        result = VisionRouter(
            [primary, codex, companion],
            VisionBackendConfig(mode="auto"),
        ).resolve(primary)

        self.assertIs(companion, result.provider)
        self.assertEqual("auto", result.mode)

    def test_specific_unready_provider_returns_clear_status(self):
        primary = custom_provider("GLM", "glm-5.1", vision=False)
        missing_key = custom_provider("Vision Missing Key", "gpt-5.5", vision=True, key="")

        result = VisionRouter(
            [primary, missing_key],
            VisionBackendConfig(mode="provider", target="Vision Missing Key"),
        ).resolve(primary)

        self.assertIsNone(result.provider)
        self.assertIn("not ready", result.status)


if __name__ == "__main__":
    unittest.main()

