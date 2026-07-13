class TaskChoiceMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class TaskChoiceDecision {
    selected_task_id: string,
    confidence: float,
    candidate_memory: root.memory.CandidateMemory?,
}
