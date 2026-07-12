client<llm> OpenCodeGoModelDeepseekV4ProReasoningNone {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-pro",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "none",
    },
}

client<llm> OpenCodeGoModelDeepseekV4ProReasoningMinimal {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-pro",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "minimal",
    },
}

client<llm> OpenCodeGoModelDeepseekV4ProReasoningLow {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-pro",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "low",
    },
}

client<llm> OpenCodeGoModelDeepseekV4ProReasoningMedium {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-pro",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "medium",
    },
}

client<llm> OpenCodeGoModelDeepseekV4ProReasoningHigh {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-pro",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "high",
    },
}

client<llm> OpenCodeGoModelDeepseekV4ProReasoningXhigh {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-pro",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "xhigh",
    },
}
