class AvailableTask {
    id: string,
    name: string,
    description: string,
    input: string,
    output: string,
    prompt: string,
    provider_id: string,
    created_at: string,
    updated_at: string,
    read_at: string,
}

class TaskChoiceMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class SelectedTaskContext {
    id: string,
    name: string,
    description: string,
    input: string,
    output: string,
    prompt: string,
    provider_id: string,
    created_at: string,
    updated_at: string,
    read_at: string,
}

class TaskChoiceDecision {
    selected_task_id: string,
    confidence: float,
    candidate_memory: root.memory_search.CandidateMemory?,
}
