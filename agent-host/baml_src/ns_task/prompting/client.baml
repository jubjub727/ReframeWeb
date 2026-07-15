client<llm> TaskPromptModel {
    provider: openai-generic,
    retry_policy: AgentFlowRetry,
    options: {
        base_url: "https://opencode.ai/zen/go/v1",
        model: "glm-5.1",
        reasoning_effort: "none",
        api_key: env.OPENCODE_GO_API_KEY,
    },
}
