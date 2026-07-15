function RelevantSessionGraph(
    session: root.memory.RetrievedSessionGraph,
    kept_ids: string[],
) -> root.memory.RetrievedSessionGraph? {
    let conversations: root.memory.RetrievedConversationGraph[] = [];
    for (let conversation in session.conversations) {
        if let filtered: root.memory.RetrievedConversationGraph = RelevantConversationGraph(conversation, kept_ids) {
            let _ = conversations.push(filtered);
        }
    }

    let session_memories = session
        .session_memories
        .filter(
            (memory) -> {
                kept_ids.includes(memory.id)
            },
        );
    let has_relevant_context = kept_ids.includes(session.session.id)
        || conversations.length() > 0
        || session_memories.length() > 0;

    if (!has_relevant_context) {
        null
    } else {
        root.memory.RetrievedSessionGraph {
            session: session.session,
            matched: session.matched,
            conversations: conversations,
            session_memories: session_memories,
        }
    }
}

function RelevantConversationGraph(
    conversation: root.memory.RetrievedConversationGraph,
    kept_ids: string[],
) -> root.memory.RetrievedConversationGraph? {
    let messages = conversation
        .messages
        .filter(
            (message) -> {
                kept_ids.includes(message.id)
            },
        );
    let has_relevant_context = kept_ids.includes(conversation.conversation.id) || messages.length() > 0;

    if (!has_relevant_context) {
        null
    } else {
        root.memory.RetrievedConversationGraph {
            conversation: conversation.conversation,
            matched: conversation.matched,
            messages: messages,
            matched_message_ids: conversation
                .matched_message_ids
                .filter(
                    (message_id) -> {
                        kept_ids.includes(message_id)
                    },
                ),
        }
    }
}
