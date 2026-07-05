from reframe_agent_host.memory_seed.opencode_go import (
    _allowed_provider_keys,
    _direct_provider,
)
from reframe_agent_host.memory_seed.opencode_go_models import OpenCodeGoModelReference


def test_direct_provider_can_omit_reasoning_effort() -> None:
    provider = _direct_provider(_kimi_reference(), None)

    assert provider.name == "OpenCode Go direct model: kimi-k2.6"
    assert provider.baml_surface == "OpenCodeGoModelKimiK26"
    assert provider.model_id == "kimi-k2.6"
    assert provider.reasoning_effort is None


def test_default_direct_provider_is_not_pruned() -> None:
    assert ("OpenCodeGoModelKimiK26", "kimi-k2.6", None) in _allowed_provider_keys()


def _kimi_reference() -> OpenCodeGoModelReference:
    return OpenCodeGoModelReference(
        model_id="kimi-k2.6",
        direct_baml_surface="OpenCodeGoModelKimiK26",
        workspace_baml_surface="OpenCodeWorkspaceModelKimiK26",
    )
