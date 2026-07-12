client<llm> OpenCodeGoModelKimiK27CodeReasoningNone {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.7-code",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "none",
    },
}

client<llm> OpenCodeGoModelKimiK27CodeReasoningMinimal {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.7-code",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "minimal",
    },
}

client<llm> OpenCodeGoModelKimiK27CodeReasoningLow {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.7-code",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "low",
    },
}

client<llm> OpenCodeGoModelKimiK27CodeReasoningMedium {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.7-code",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "medium",
    },
}

client<llm> OpenCodeGoModelKimiK27CodeReasoningHigh {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.7-code",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "high",
    },
}

client<llm> OpenCodeGoModelKimiK27CodeReasoningXhigh {
    provider: openai-generic,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.7-code",
        api_key: env.OPENCODE_GO_API_KEY,
        reasoning_effort: "xhigh",
    },
}
