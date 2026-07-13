class ModelReference {
    model_id: string,
    direct_baml_surface: string,
    workspace_baml_surface: string,
    reasoning_efforts: string[],
}

//# List reasoning

function StandardReasoningEfforts() -> string[] {
    ["none", "minimal", "low", "medium", "high", "xhigh"]
}

//# Build model list

function ModelInventory() -> ModelReference[] {
    let standard = StandardReasoningEfforts();
    [
        ModelReference {
            model_id: "kimi-k2.7-code",
            direct_baml_surface: "opencode_go.OpenCodeGoModelKimiK27Code",
            workspace_baml_surface: "OpenCodeWorkspaceModelKimiK27Code",
            reasoning_efforts: standard,
        },
        ModelReference {
            model_id: "kimi-k2.6",
            direct_baml_surface: "opencode_go.OpenCodeGoModelKimiK26",
            workspace_baml_surface: "OpenCodeWorkspaceModelKimiK26",
            reasoning_efforts: standard,
        },
        ModelReference {
            model_id: "kimi-k2.5",
            direct_baml_surface: "opencode_go.OpenCodeGoModelKimiK25",
            workspace_baml_surface: "OpenCodeWorkspaceModelKimiK25",
            reasoning_efforts: standard,
        },
        ModelReference {
            model_id: "glm-5.1",
            direct_baml_surface: "opencode_go.OpenCodeGoModelGlm51",
            workspace_baml_surface: "OpenCodeWorkspaceModelGlm51",
            reasoning_efforts: standard,
        },
        ModelReference {
            model_id: "glm-5",
            direct_baml_surface: "opencode_go.OpenCodeGoModelGlm5",
            workspace_baml_surface: "OpenCodeWorkspaceModelGlm5",
            reasoning_efforts: standard,
        },
        ModelReference {
            model_id: "deepseek-v4-pro",
            direct_baml_surface: "opencode_go.OpenCodeGoModelDeepseekV4Pro",
            workspace_baml_surface: "OpenCodeWorkspaceModelDeepseekV4Pro",
            reasoning_efforts: standard,
        },
        ModelReference {
            model_id: "deepseek-v4-flash",
            direct_baml_surface: "opencode_go.OpenCodeGoModelDeepseekV4Flash",
            workspace_baml_surface: "OpenCodeWorkspaceModelDeepseekV4Flash",
            reasoning_efforts: ["none", "minimal", "low", "medium", "high", "max"],
        },
        ModelReference {
            model_id: "mimo-v2.5-pro",
            direct_baml_surface: "opencode_go.OpenCodeGoModelMimoV25Pro",
            workspace_baml_surface: "OpenCodeWorkspaceModelMimoV25Pro",
            reasoning_efforts: standard,
        },
        ModelReference {
            model_id: "mimo-v2.5",
            direct_baml_surface: "opencode_go.OpenCodeGoModelMimoV25",
            workspace_baml_surface: "OpenCodeWorkspaceModelMimoV25",
            reasoning_efforts: standard,
        },
    ]
}

test "model inventory matches direct BAML clients" {
    let models = ModelInventory();
    assert.equal(models.length(), 9);
    assert.equal(models[3].model_id, "glm-5.1");
    assert.equal(models[3].direct_baml_surface, "opencode_go.OpenCodeGoModelGlm51");
    assert.equal(models[6].reasoning_efforts.includes("max"), true)
}
