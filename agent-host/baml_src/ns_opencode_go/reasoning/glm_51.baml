client<llm> OpenCodeGoModelGlm51ReasoningNone {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "glm-5.1",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "none",
    },
}

client<llm> OpenCodeGoModelGlm51ReasoningMinimal {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "glm-5.1",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "minimal",
    },
}

client<llm> OpenCodeGoModelGlm51ReasoningLow {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "glm-5.1",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "low",
    },
}

client<llm> OpenCodeGoModelGlm51ReasoningMedium {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "glm-5.1",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "medium",
    },
}

client<llm> OpenCodeGoModelGlm51ReasoningHigh {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "glm-5.1",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "high",
    },
}

client<llm> OpenCodeGoModelGlm51ReasoningXhigh {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "glm-5.1",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "xhigh",
    },
}
