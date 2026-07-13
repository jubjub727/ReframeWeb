client<llm> TaskChoiceModel {
    provider: openai-generic,
    retry_policy: AgentFlowRetry,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "kimi-k2.5",
        reasoning_effort: "high",
        api_key: env.OPENCODE_GO_API_KEY,
    },
}
