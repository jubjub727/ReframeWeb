class ConversationEvaluationMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class SearchDepthMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class MemoryTagSearch {
    any_of: string[],
    all_of: string[],
    none_of: string[],
}

class MemoryStringSearch {
    contains: string[],
    equals: string[],
}

class CandidateMemory {
    title: string,
    description: string,
}

class SearchDepthDomain {
    id: string,
    description: string,
    searches: string,
    hydrates: string,
}

class SearchDepthTimestamps {
    created_after: string,
    read_after: string,
    updated_after: string,
}

class ConversationMemorySearchHints {
    tags: MemoryTagSearch,
    strings: MemoryStringSearch,
    candidate_memory: CandidateMemory?,
}

class SearchDepthDecision {
    depths: map<string, SearchDepthTimestamps>,
    candidate_memory: CandidateMemory?,
}
