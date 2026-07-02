client<llm> TaskChoiceModel {
  provider openai-generic
  retry_policy AgentFlowRetry
  options {
    base_url "https://opencode.ai/zen/go/v1"
    model "deepseek-v4-flash"
    api_key env.OPENCODE_GO_API_KEY
  }
}

client<llm> ConversationEvaluationModel {
  provider openai-generic
  retry_policy AgentFlowRetry
  options {
    base_url "https://opencode.ai/zen/go/v1"
    model "glm-5.1"
    api_key env.OPENCODE_GO_API_KEY
  }
}

retry_policy AgentFlowRetry {
  max_retries 2
  strategy {
    type exponential_backoff
    delay_ms 300
    multiplier 1.5
    max_delay_ms 10000
  }
}
