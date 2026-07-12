from __future__ import annotations

from dataclasses import dataclass


OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go/v1"
OPENCODE_GO_REASONING_EFFORTS = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
)
OPENCODE_GO_DEEPSEEK_V4_FLASH_REASONING_EFFORTS = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "max",
)


@dataclass(frozen=True)
class OpenCodeGoModelReference:
    model_id: str
    direct_baml_surface: str
    workspace_baml_surface: str
    reasoning_efforts: tuple[str, ...] = OPENCODE_GO_REASONING_EFFORTS


def opencode_go_model_inventory() -> tuple[OpenCodeGoModelReference, ...]:
    return (
        OpenCodeGoModelReference(
            "kimi-k2.7-code",
            "opencode_go.OpenCodeGoModelKimiK27Code",
            "OpenCodeWorkspaceModelKimiK27Code",
        ),
        OpenCodeGoModelReference(
            "kimi-k2.6",
            "opencode_go.OpenCodeGoModelKimiK26",
            "OpenCodeWorkspaceModelKimiK26",
        ),
        OpenCodeGoModelReference(
            "kimi-k2.5",
            "opencode_go.OpenCodeGoModelKimiK25",
            "OpenCodeWorkspaceModelKimiK25",
        ),
        OpenCodeGoModelReference(
            "glm-5.1",
            "opencode_go.OpenCodeGoModelGlm51",
            "OpenCodeWorkspaceModelGlm51",
        ),
        OpenCodeGoModelReference(
            "glm-5",
            "opencode_go.OpenCodeGoModelGlm5",
            "OpenCodeWorkspaceModelGlm5",
        ),
        OpenCodeGoModelReference(
            "deepseek-v4-pro",
            "opencode_go.OpenCodeGoModelDeepseekV4Pro",
            "OpenCodeWorkspaceModelDeepseekV4Pro",
        ),
        OpenCodeGoModelReference(
            "deepseek-v4-flash",
            "opencode_go.OpenCodeGoModelDeepseekV4Flash",
            "OpenCodeWorkspaceModelDeepseekV4Flash",
            OPENCODE_GO_DEEPSEEK_V4_FLASH_REASONING_EFFORTS,
        ),
        OpenCodeGoModelReference(
            "mimo-v2.5-pro",
            "opencode_go.OpenCodeGoModelMimoV25Pro",
            "OpenCodeWorkspaceModelMimoV25Pro",
        ),
        OpenCodeGoModelReference(
            "mimo-v2.5",
            "opencode_go.OpenCodeGoModelMimoV25",
            "OpenCodeWorkspaceModelMimoV25",
        ),
    )
