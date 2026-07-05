client<llm> TaskChoiceModel {
  provider openai-generic
  retry_policy AgentFlowRetry
  options {
    base_url "https://opencode.ai/zen/go/v1"
    model "kimi-k2.5"
    reasoning_effort "high"
    api_key env.OPENCODE_GO_API_KEY
  }
}

client<llm> ConversationEvaluationModel {
  provider openai-generic
  retry_policy AgentFlowRetry
  options {
    base_url "https://opencode.ai/zen/go/v1"
    model "glm-5.1"
    reasoning_effort "none"
    api_key env.OPENCODE_GO_API_KEY
  }
}

client<llm> SearchDepthModel {
  provider openai-generic
  retry_policy AgentFlowRetry
  options {
    base_url "https://opencode.ai/zen/go/v1"
    model "glm-5.1"
    reasoning_effort "none"
    api_key env.OPENCODE_GO_API_KEY
  }
}

client<llm> RelevanceModel {
  provider openai-generic
  retry_policy AgentFlowRetry
  options {
    base_url "https://opencode.ai/zen/go/v1"
    model "glm-5.1"
    reasoning_effort "none"
    api_key env.OPENCODE_GO_API_KEY
  }
}

client<llm> TaskPromptModel {
  provider openai-generic
  retry_policy AgentFlowRetry
  options {
    base_url "https://opencode.ai/zen/go/v1"
    model "kimi-k2.6"
    reasoning_effort "none"
    api_key env.OPENCODE_GO_API_KEY
  }
}

client<llm> TaskExecutionModel {
  provider openai-generic
  retry_policy AgentFlowRetry
  options {
    base_url "https://opencode.ai/zen/go/v1"
    model "kimi-k2.6"
    reasoning_effort "none"
    api_key env.OPENCODE_GO_API_KEY
  }
}

retry_policy AgentFlowRetry {
  max_retries 2
  initial_delay_ms 300
  multiplier 1.5
  max_delay_ms 10000
}
