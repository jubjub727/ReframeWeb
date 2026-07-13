//# Build message

function Message(
    role: string,
    content: string,
    created_at: string,
) -> BenchmarkConversationMessage {
    BenchmarkConversationMessage {
        created_at: created_at,
        updated_at: created_at,
        read_at: "NONE",
        role: role,
        content: content,
    }
}

//# Build conversation

function Conversation(
    id_suffix: string,
    name: string,
    messages: BenchmarkConversationMessage[],
) -> BenchmarkConversation {
    BenchmarkConversation {
        id: `benchmark_conversation:${id_suffix}`,
        name: name,
        created_at: messages[0].created_at,
        updated_at: messages[messages.length() - 1].updated_at,
        read_at: "NONE",
        messages: messages,
    }
}

//# Build memory

function Memory(
    title: string,
    description: string,
    tags: string[],
    created_at: string,
) -> BenchmarkMemory {
    BenchmarkMemory {
        title: title,
        description: description,
        tags: tags,
        created_at: created_at,
        updated_at: created_at,
        read_at: "NONE",
    }
}

//# Build session

function Session(
    id_suffix: string,
    name: string,
    conversations: BenchmarkConversation[],
    memories: BenchmarkMemory[],
) -> BenchmarkSession {
    let timestamps = conversations
        .map(
            (conversation) -> {
                conversation.created_at
            },
        )
        .concat(
            memories
                .map(
                    (memory) -> {
                        memory.created_at
                    },
                ),
        );
    let updated_timestamps = conversations
        .map(
            (conversation) -> {
                conversation.updated_at
            },
        )
        .concat(
            memories
                .map(
                    (memory) -> {
                        memory.updated_at
                    },
                ),
        );
    timestamps.sort();
    updated_timestamps.sort();
    BenchmarkSession {
        id: `benchmark_session:${id_suffix}`,
        name: name,
        created_at: timestamps[0],
        updated_at: updated_timestamps[updated_timestamps.length() - 1],
        read_at: "NONE",
        conversations: conversations,
        memories: memories,
    }
}
