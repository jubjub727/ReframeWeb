enum CandidateMemoryLayer {
    TASK_CHOICE,
    CONVERSATION_EVALUATION,
    SEARCH_DEPTH,
    RELEVANCE,
    TASK_PROMPT,
}

class CandidateMemoryEntry {
    id: string,
    title: string,
    description: string,
}

class CandidateMemoryGroups {
    task_choice: CandidateMemoryEntry[],
    conversation_evaluation: CandidateMemoryEntry[],
    search_depth: CandidateMemoryEntry[],
    relevance: CandidateMemoryEntry[],
    task_prompt: CandidateMemoryEntry[],
}

class StoredCandidateMemory {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class CandidateMemoryReviewContext {
    task_choice: StoredCandidateMemory[],
    conversation_evaluation: StoredCandidateMemory[],
    search_depth: StoredCandidateMemory[],
    relevance: StoredCandidateMemory[],
    task_prompt: StoredCandidateMemory[],
}

class CandidateMemoryReviewDecision {
    kept_candidate_ids: string[],
}

class CandidateMemoryWriteBatch {
    task_choice: CandidateMemoryEntry[],
    conversation_evaluation: CandidateMemoryEntry[],
    search_depth: CandidateMemoryEntry[],
    relevance: CandidateMemoryEntry[],
    task_prompt: CandidateMemoryEntry[],
}
