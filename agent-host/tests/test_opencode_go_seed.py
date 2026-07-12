import unittest

from reframe_agent_host.memory_seed.opencode_go import (
    _allowed_provider_keys,
    _direct_provider,
)
from reframe_agent_host.memory_seed.opencode_go_models import OpenCodeGoModelReference


class OpenCodeGoSeedTests(unittest.TestCase):
    def test_direct_provider_can_omit_reasoning_effort(self) -> None:
        provider = _direct_provider(_kimi_reference(), None)

        self.assertEqual(provider.name, "OpenCode Go direct model: kimi-k2.6")
        self.assertEqual(provider.baml_surface, "opencode_go.OpenCodeGoModelKimiK26")
        self.assertEqual(provider.model_id, "kimi-k2.6")
        self.assertIsNone(provider.reasoning_effort)

    def test_default_direct_provider_is_not_pruned(self) -> None:
        allowed = _allowed_provider_keys()
        self.assertIn(("opencode_go.OpenCodeGoModelKimiK26", "kimi-k2.6", None), allowed)
        self.assertIn(("opencode_go.OpenCodeGoModelKimiK26", "kimi-k2.6", "xhigh"), allowed)

    def test_deepseek_flash_uses_max_instead_of_xhigh(self) -> None:
        allowed = _allowed_provider_keys()
        self.assertIn(
            (
                "opencode_go.OpenCodeGoModelDeepseekV4Flash",
                "deepseek-v4-flash",
                "max",
            ),
            allowed,
        )
        self.assertNotIn(
            (
                "opencode_go.OpenCodeGoModelDeepseekV4Flash",
                "deepseek-v4-flash",
                "xhigh",
            ),
            allowed,
        )


def _kimi_reference() -> OpenCodeGoModelReference:
    return OpenCodeGoModelReference(
        model_id="kimi-k2.6",
        direct_baml_surface="opencode_go.OpenCodeGoModelKimiK26",
        workspace_baml_surface="OpenCodeWorkspaceModelKimiK26",
    )


if __name__ == "__main__":
    unittest.main()
