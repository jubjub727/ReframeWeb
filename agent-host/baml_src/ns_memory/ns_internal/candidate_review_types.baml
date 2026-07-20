class CandidateMemoryReviewInput {
    layer: root.memory.CandidateMemoryLayer,
    purpose: string,
    candidates: root.memory.CandidateMemoryEntry[],
    stored_memories: root.memory.StoredCandidateMemory[],
}

class CandidateMemoryReview {
    layer: root.memory.CandidateMemoryLayer,
    candidates: root.memory.CandidateMemoryEntry[],
    kept_candidates: root.memory.CandidateMemoryEntry[],
}
