client<llm> OpenCodeGoModelDeepseekV4FlashReasoningNone {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-flash",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "none",
    },
}

client<llm> OpenCodeGoModelDeepseekV4FlashReasoningMinimal {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-flash",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "minimal",
    },
}

client<llm> OpenCodeGoModelDeepseekV4FlashReasoningLow {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-flash",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "low",
    },
}

client<llm> OpenCodeGoModelDeepseekV4FlashReasoningMedium {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-flash",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "medium",
    },
}

client<llm> OpenCodeGoModelDeepseekV4FlashReasoningHigh {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-flash",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "high",
    },
}

client<llm> OpenCodeGoModelDeepseekV4FlashReasoningMax {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "deepseek-v4-flash",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "max",
    },
}
