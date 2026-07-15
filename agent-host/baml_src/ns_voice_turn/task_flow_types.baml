class VoiceTaskFlowContext {
    cycle_id: string,
    current_timestamp: string,
    current_conversation: root.turn_context.ConversationHistory?,
    session_memories: root.turn_context.SessionMemoryContext[],
    user_preferences: root.turn_context.UserPreferenceMemoryContext[],
    available_tasks: root.task_catalog.AvailableTask[],
    task_choice_memories: root.task.TaskChoiceMemoryContext[],
    conversation_evaluation_memories: root.memory.ConversationEvaluationMemoryContext[],
    search_depth_memories: root.memory.SearchDepthMemoryContext[],
    current_session_id: string?,
    relevance_memories: root.memory.RelevanceMemoryContext[],
    task_prompt_memories: root.task.TaskPromptMemoryContext[],
    machine_state: root.turn_context.MachineStateContext,
}

class VoiceTaskExecutionBoundaryResult {
    attempt_id: string,
    task_execution: root.task.TaskExecutionResult?,
}

class VoiceTaskFlowResult {
    cycle_id: string,
    understanding: VoicePromptUnderstanding,
    retrieved_memories: root.memory.RetrievedMemoryGraph,
    continuation: VoicePromptContinuation,
    attempt_id: string,
    task_completion: root.task.CompletionResult,
    task_completion_ms: bigint,
}
