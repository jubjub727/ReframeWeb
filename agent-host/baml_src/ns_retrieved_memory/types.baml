class RetrievedTaskNode {
    id: string,
    name: string,
    description: string,
    input: string,
    output: string,
    prompt: string,
    provider_id: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RetrievedSessionNode {
    id: string,
    name: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RetrievedSessionMemoryNode {
    id: string,
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RetrievedConversationNode {
    id: string,
    name: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RetrievedConversationMessageNode {
    id: string,
    role: string,
    content: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RetrievedConversationGraph {
    conversation: RetrievedConversationNode,
    matched: bool,
    messages: RetrievedConversationMessageNode[],
    matched_message_ids: string[],
}

class RetrievedSessionGraph {
    session: RetrievedSessionNode,
    matched: bool,
    conversations: RetrievedConversationGraph[],
    session_memories: RetrievedSessionMemoryNode[],
}

class RetrievedMemoryGraph {
    task_catalog: RetrievedTaskNode[],
    past_sessions: RetrievedSessionGraph[],
    current_session_memories: RetrievedSessionMemoryNode[],
}
