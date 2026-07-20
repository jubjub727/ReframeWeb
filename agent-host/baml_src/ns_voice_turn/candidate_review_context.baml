function MemoryReviewContext(
    context: VoiceTaskFlowContext,
) -> root.memory.CandidateMemoryReviewContext {
    root.memory.CandidateMemoryReviewContext {
        task_choice: context
            .task_choice_memories
            .map(
                (memory) -> {
                    StoredCandidateMemory(
                        memory.title,
                        memory.description,
                        memory.tags,
                        memory.created_at,
                        memory.updated_at,
                        memory.read_at,
                    )
                },
            ),
        conversation_evaluation: context
            .conversation_evaluation_memories
            .map(
                (memory) -> {
                    StoredCandidateMemory(
                        memory.title,
                        memory.description,
                        memory.tags,
                        memory.created_at,
                        memory.updated_at,
                        memory.read_at,
                    )
                },
            ),
        search_depth: context
            .search_depth_memories
            .map(
                (memory) -> {
                    StoredCandidateMemory(
                        memory.title,
                        memory.description,
                        memory.tags,
                        memory.created_at,
                        memory.updated_at,
                        memory.read_at,
                    )
                },
            ),
        relevance: context
            .relevance_memories
            .map(
                (memory) -> {
                    StoredCandidateMemory(
                        memory.title,
                        memory.description,
                        memory.tags,
                        memory.created_at,
                        memory.updated_at,
                        memory.read_at,
                    )
                },
            ),
        task_prompt: context
            .task_prompt_memories
            .map(
                (memory) -> {
                    StoredCandidateMemory(
                        memory.title,
                        memory.description,
                        memory.tags,
                        memory.created_at,
                        memory.updated_at,
                        memory.read_at,
                    )
                },
            ),
    }
}

function StoredCandidateMemory(
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
) -> root.memory.StoredCandidateMemory {
    root.memory.StoredCandidateMemory {
        title: title,
        description: description,
        tags: tags,
        created_at: created_at,
        updated_at: updated_at,
        read_at: read_at,
    }
}
