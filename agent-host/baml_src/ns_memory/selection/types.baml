class RelevanceMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RetrievedMemoryCandidate {
    id: string,
    kind: string,
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
    retrieval_matched: bool,
    parent_session_id: string?,
    parent_conversation_id: string?,
}

class RelevantMemoryDecision {
    kept_memory_ids: string[],
    candidate_memory: root.memory.CandidateMemory?,
}
