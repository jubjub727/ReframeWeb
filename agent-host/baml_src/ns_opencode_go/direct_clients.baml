client<llm> OpenCodeGoModelKimiK27Code {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.7-code",
        api_key: env.OPENCODE_GO_API_KEY,
    },
}

client<llm> OpenCodeGoModelKimiK26 {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.6",
        api_key: env.OPENCODE_GO_API_KEY,
    },
}

client<llm> OpenCodeGoModelKimiK25 {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.5",
        api_key: env.OPENCODE_GO_API_KEY,
    },
}

client<llm> OpenCodeGoModelGlm51 {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "glm-5.1",
        api_key: env.OPENCODE_GO_API_KEY,
    },
}

client<llm> OpenCodeGoModelGlm5 {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "glm-5",
        api_key: env.OPENCODE_GO_API_KEY,
    },
}

client<llm> OpenCodeGoModelDeepseekV4Pro {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-pro",
        api_key: env.OPENCODE_GO_API_KEY,
    },
}

client<llm> OpenCodeGoModelDeepseekV4Flash {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-flash",
        api_key: env.OPENCODE_GO_API_KEY,
    },
}

client<llm> OpenCodeGoModelMimoV25Pro {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "mimo-v2.5-pro",
        api_key: env.OPENCODE_GO_API_KEY,
    },
}

client<llm> OpenCodeGoModelMimoV25 {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "mimo-v2.5",
        api_key: env.OPENCODE_GO_API_KEY,
    },
}
