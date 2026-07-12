enum ConversationMode {
    WAKE_COMMAND,
    CONTINUOUS_CONVERSATION,
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
