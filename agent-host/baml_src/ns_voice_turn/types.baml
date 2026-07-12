class VoicePromptUnderstanding {
    task_choice: root.task_routing.TaskChoiceDecision,
    selected_task: root.task_routing.SelectedTaskContext,
    memory_search_hints: root.memory_search.ConversationMemorySearchHints,
    search_depths: root.memory_search.SearchDepthDecision,
    timings: VoicePromptUnderstandingTimings,
}

class VoicePromptContinuation {
    relevance_decision: root.memory_selection.RelevantMemoryDecision,
    selected_memories: root.retrieved_memory.RetrievedMemoryGraph,
    selected_memory_contexts: root.task_prompt.TaskPromptSelectedMemoryContext[],
    task_prompt: root.task_prompt.TaskPromptDecision,
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
