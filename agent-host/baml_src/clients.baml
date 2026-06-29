client<llm> AgentFlowModel {
  provider openai-responses
  retry_policy AgentFlowRetry
  options {
    model env.REFRAME_AGENT_MODEL
    api_key env.OPENAI_API_KEY
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
