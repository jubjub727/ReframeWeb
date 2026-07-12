client<llm> OpenCodeGoModelKimiK26ReasoningNone {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.6",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "none",
    },
}

client<llm> OpenCodeGoModelKimiK26ReasoningMinimal {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.6",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "minimal",
    },
}

client<llm> OpenCodeGoModelKimiK26ReasoningLow {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.6",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "low",
    },
}

client<llm> OpenCodeGoModelKimiK26ReasoningMedium {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.6",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "medium",
    },
}

client<llm> OpenCodeGoModelKimiK26ReasoningHigh {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.6",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "high",
    },
}

client<llm> OpenCodeGoModelKimiK26ReasoningXhigh {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.6",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "xhigh",
    },
}
