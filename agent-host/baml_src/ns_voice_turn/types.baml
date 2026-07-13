class VoicePromptUnderstanding {
    task_choice: root.task.TaskChoiceDecision,
    selected_task: root.task_catalog.SelectedTaskContext,
    memory_search_hints: root.memory.ConversationMemorySearchHints,
    search_depths: root.memory.SearchDepthDecision,
    timings: VoicePromptUnderstandingTimings,
}

class VoicePromptContinuation {
    relevance_decision: root.memory.RelevantMemoryDecision,
    selected_memories: root.memory.RetrievedMemoryGraph,
    selected_memory_contexts: root.task.TaskPromptSelectedMemoryContext[],
    task_prompt: root.task.TaskPromptDecision,
    timings: VoicePromptContinuationTimings,
}

class VoicePromptUnderstandingTimings {
    task_choice_ms: bigint,
    memory_search_ms: bigint,
    search_depth_ms: bigint,
}

class VoicePromptContinuationTimings {
    memory_relevance_ms: bigint,
    task_prompt_ms: bigint,
}
