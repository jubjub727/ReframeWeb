function EmptyCandidateMemoryWriteBatch() -> root.memory.CandidateMemoryWriteBatch {
    root.memory.CandidateMemoryWriteBatch {
        task_choice: [],
        conversation_evaluation: [],
        search_depth: [],
        relevance: [],
        task_prompt: [],
    }
}

function CandidateMemoryCount(groups: root.memory.CandidateMemoryGroups) -> int {
    groups.task_choice.length()
        + groups.conversation_evaluation.length()
        + groups.search_depth.length()
        + groups.relevance.length()
        + groups.task_prompt.length()
}

function AddCandidateMemoryToGroup(
    group: root.memory.CandidateMemoryEntry[],
    layer: root.memory.CandidateMemoryLayer,
    candidate: root.memory.CandidateMemory,
) -> void {
    group
        .push(
            root.memory.CandidateMemoryEntry {
                id: `${layer.to_string().to_lower_case()}-${group.length() + 1}`,
                title: candidate.title,
                description: candidate.description,
            },
        );
}

function HasSelectedCandidates(batch: root.memory.CandidateMemoryWriteBatch) -> bool {
    batch.task_choice.length()
        + batch.conversation_evaluation.length()
        + batch.search_depth.length()
        + batch.relevance.length()
        + batch.task_prompt.length()
        > 0
}
