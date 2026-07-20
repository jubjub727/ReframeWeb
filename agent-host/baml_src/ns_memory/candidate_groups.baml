function EmptyCandidateMemoryGroups() -> CandidateMemoryGroups {
    CandidateMemoryGroups {
        task_choice: [],
        conversation_evaluation: [],
        search_depth: [],
        relevance: [],
        task_prompt: [],
    }
}

function AddCandidateMemory(
    groups: CandidateMemoryGroups,
    layer: CandidateMemoryLayer,
    candidate: CandidateMemory?,
) -> void {
    if let memory: CandidateMemory = candidate {
        match (layer) {
            CandidateMemoryLayer.TASK_CHOICE => {
                root.memory.internal.AddCandidateMemoryToGroup(groups.task_choice, layer, memory)
            },
            CandidateMemoryLayer.CONVERSATION_EVALUATION => {
                root.memory
                    .internal
                    .AddCandidateMemoryToGroup(groups.conversation_evaluation, layer, memory)
            },
            CandidateMemoryLayer.SEARCH_DEPTH => {
                root.memory.internal.AddCandidateMemoryToGroup(groups.search_depth, layer, memory)
            },
            CandidateMemoryLayer.RELEVANCE => {
                root.memory.internal.AddCandidateMemoryToGroup(groups.relevance, layer, memory)
            },
            CandidateMemoryLayer.TASK_PROMPT => {
                root.memory.internal.AddCandidateMemoryToGroup(groups.task_prompt, layer, memory)
            },
        }
    }
}
