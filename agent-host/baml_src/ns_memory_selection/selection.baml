function SelectedGraph(
    memories: root.retrieved_memory.RetrievedMemoryGraph,
    decision: root.memory_selection.RelevantMemoryDecision,
) -> root.retrieved_memory.RetrievedMemoryGraph {
    let kept_ids = decision.kept_memory_ids;
    let sessions: root.retrieved_memory.RetrievedSessionGraph[] = [];

    for (let session in memories.past_sessions) {
        if let filtered: root.retrieved_memory.RetrievedSessionGraph = RelevantSessionGraph(session, kept_ids) {
            let _ = sessions.push(filtered);
        }
    }

    root.retrieved_memory.RetrievedMemoryGraph {
        task_catalog: memories
            .task_catalog
            .filter(
                (task) -> {
                    kept_ids.includes(task.id)
                },
            ),
        past_sessions: sessions,
        current_session_memories: memories
            .current_session_memories
            .filter(
                (memory) -> {
                    kept_ids.includes(memory.id)
                },
            ),
    }
}

function RelevantSessionGraph(
    session: root.retrieved_memory.RetrievedSessionGraph,
    kept_ids: string[],
) -> root.retrieved_memory.RetrievedSessionGraph? {
    let conversations: root.retrieved_memory.RetrievedConversationGraph[] = [];
    for (let conversation in session.conversations) {
        if let filtered: root.retrieved_memory.RetrievedConversationGraph = RelevantConversationGraph(conversation, kept_ids) {
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
    if (
        !kept_ids.includes(session.session.id)
            && conversations.length() == 0
            && session_memories.length() == 0
    ) {
        null
    } else {
        root.retrieved_memory.RetrievedSessionGraph {
            session: session.session,
            matched: session.matched,
            conversations: conversations,
            session_memories: session_memories,
        }
    }
}

function RelevantConversationGraph(
    conversation: root.retrieved_memory.RetrievedConversationGraph,
    kept_ids: string[],
) -> root.retrieved_memory.RetrievedConversationGraph? {
    let messages = conversation
        .messages
        .filter(
            (message) -> {
                kept_ids.includes(message.id)
            },
        );
    if (!kept_ids.includes(conversation.conversation.id) && messages.length() == 0) {
        null
    } else {
        root.retrieved_memory.RetrievedConversationGraph {
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
