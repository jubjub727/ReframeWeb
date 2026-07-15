class TaskPromptMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class TaskPromptSelectedMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class TaskPromptDecision {
    full_task_prompt: string,
    candidate_memory: root.memory.CandidateMemory?,
}

class TaskPromptComposition {
    task_input: string,
    candidate_memory: root.memory.CandidateMemory?,
}

class TaskAttemptReply {
    role: string,
    content: string,
}
