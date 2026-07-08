enum ConversationMode {
    WAKE_COMMAND,
    CONTINUOUS_CONVERSATION,
}

enum CompletionResult {
    PASS,
    FAIL,
}

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

class ConversationHistoryMessage {
    created_at: string,
    updated_at: string,
    read_at: string,
    role: string,
    content: string,
}

class ConversationHistory {
    id: string,
    name: string,
    created_at: string,
    updated_at: string,
    read_at: string,
    messages: ConversationHistoryMessage[],
}

class SessionMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class UserPreferenceMemoryContext {
    id: string,
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class MachineMonitorContext {
    horizontal_resolution: int,
    vertical_resolution: int,
}

class MachineStateContext {
    captured_at_utc: string,
    current_local_time: string,
    current_utc_time: string,
    timezone_name: string,
    utc_offset: string,
    os_architecture: string,
    monitor_count: int,
    monitors: MachineMonitorContext[],
    geolocation_status: string,
    geolocation_source: string?,
    ip_address: string?,
    country: string?,
    country_code: string?,
    region: string?,
    city: string?,
    postal_code: string?,
    latitude: string?,
    longitude: string?,
    geolocation_timezone: string?,
    organization: string?,
    asn: string?,
    geolocation_error: string?,
}

class TaskChoiceMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

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

class RelevanceMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class TaskPromptMemoryContext {
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

class TaskPromptSelectedMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RelevantMemoryDecision {
    kept_memory_ids: string[],
    candidate_memory: CandidateMemory?,
}

class TaskChoiceDecision {
    selected_task_id: string,
    confidence: float,
    candidate_memory: CandidateMemory?,
}

class TaskPromptDecision {
    full_task_prompt: string,
    candidate_memory: CandidateMemory?,
}

class TaskPromptComposition {
    task_input: string,
    candidate_memory: CandidateMemory?,
}

class TaskReturnItem {
    name: string,
    payload: map<string, string>?,
}

class TaskExecutionResult {
    returns: TaskReturnItem[],
}
