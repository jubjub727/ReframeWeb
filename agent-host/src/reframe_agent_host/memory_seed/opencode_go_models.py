from __future__ import annotations

from dataclasses import dataclass


OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go/v1"


@dataclass(frozen=True)
class OpenCodeGoModelReference:
    model_id: str
    direct_baml_surface: str
    workspace_baml_surface: str


def opencode_go_model_inventory() -> tuple[OpenCodeGoModelReference, ...]:
    return (
        OpenCodeGoModelReference(
            "kimi-k2.7-code",
            "OpenCodeGoModelKimiK27Code",
            "OpenCodeWorkspaceModelKimiK27Code",
        ),
        OpenCodeGoModelReference(
            "kimi-k2.6",
            "OpenCodeGoModelKimiK26",
            "OpenCodeWorkspaceModelKimiK26",
        ),
        OpenCodeGoModelReference(
            "kimi-k2.5",
            "OpenCodeGoModelKimiK25",
            "OpenCodeWorkspaceModelKimiK25",
        ),
        OpenCodeGoModelReference(
            "glm-5.1",
            "OpenCodeGoModelGlm51",
            "OpenCodeWorkspaceModelGlm51",
        ),
        OpenCodeGoModelReference(
            "glm-5",
            "OpenCodeGoModelGlm5",
            "OpenCodeWorkspaceModelGlm5",
        ),
        OpenCodeGoModelReference(
            "deepseek-v4-pro",
            "OpenCodeGoModelDeepseekV4Pro",
            "OpenCodeWorkspaceModelDeepseekV4Pro",
        ),
        OpenCodeGoModelReference(
            "deepseek-v4-flash",
            "OpenCodeGoModelDeepseekV4Flash",
            "OpenCodeWorkspaceModelDeepseekV4Flash",
        ),
        OpenCodeGoModelReference(
            "mimo-v2.5-pro",
            "OpenCodeGoModelMimoV25Pro",
            "OpenCodeWorkspaceModelMimoV25Pro",
        ),
        OpenCodeGoModelReference(
            "mimo-v2.5",
            "OpenCodeGoModelMimoV25",
            "OpenCodeWorkspaceModelMimoV25",
        ),
    )
