function SessionCandidate(
    session: root.retrieved_memory.RetrievedSessionGraph,
    is_current_session: bool,
) -> root.memory_selection.RetrievedMemoryCandidate {
    root.memory_selection.RetrievedMemoryCandidate {
        id: session.session.id,
        kind: if (is_current_session) {
            "current_session"
        } else {
            "past_session"
        },
        title: session.session.name,
        description: if (is_current_session) {
            "Current session wrapper."
        } else {
            "Past session wrapper."
        },
        tags: session.session.tags,
        created_at: session.session.created_at,
        updated_at: session.session.updated_at,
        read_at: session.session.read_at,
        retrieval_matched: session.matched,
        parent_session_id: null,
        parent_conversation_id: null,
    }
}

function SessionMemoryCandidate(
    session: root.retrieved_memory.RetrievedSessionGraph,
    memory: root.retrieved_memory.RetrievedSessionMemoryNode,
    is_current_session: bool,
) -> root.memory_selection.RetrievedMemoryCandidate {
    root.memory_selection.RetrievedMemoryCandidate {
        id: memory.id,
        kind: if (is_current_session) {
            "current_session_memory"
        } else {
            "past_session_memory"
        },
        title: memory.title,
        description: memory.description,
        tags: memory.tags,
        created_at: memory.created_at,
        updated_at: memory.updated_at,
        read_at: memory.read_at,
        retrieval_matched: true,
        parent_session_id: session.session.id,
        parent_conversation_id: null,
    }
}

function ConversationCandidate(
    session: root.retrieved_memory.RetrievedSessionGraph,
    conversation: root.retrieved_memory.RetrievedConversationGraph,
    is_current_session: bool,
) -> root.memory_selection.RetrievedMemoryCandidate {
    root.memory_selection.RetrievedMemoryCandidate {
        id: conversation.conversation.id,
        kind: if (is_current_session) {
            "current_conversation"
        } else {
            "past_conversation"
        },
        title: conversation.conversation.name,
        description: if (is_current_session) {
            "Current conversation wrapper."
        } else {
            "Past conversation wrapper."
        },
        tags: conversation.conversation.tags,
        created_at: conversation.conversation.created_at,
        updated_at: conversation.conversation.updated_at,
        read_at: conversation.conversation.read_at,
        retrieval_matched: conversation.matched,
        parent_session_id: session.session.id,
        parent_conversation_id: null,
    }
}

function ConversationMessageCandidate(
    session: root.retrieved_memory.RetrievedSessionGraph,
    conversation: root.retrieved_memory.RetrievedConversationGraph,
    message: root.retrieved_memory.RetrievedConversationMessageNode,
    is_current_session: bool,
) -> root.memory_selection.RetrievedMemoryCandidate {
    root.memory_selection.RetrievedMemoryCandidate {
        id: message.id,
        kind: if (is_current_session) {
            "current_conversation_message"
        } else {
            "past_conversation_message"
        },
        title: `${message.role} message`,
        description: message.content,
        tags: message.tags,
        created_at: message.created_at,
        updated_at: message.updated_at,
        read_at: message.read_at,
        retrieval_matched: MessageMatchedMemorySearch(conversation, message),
        parent_session_id: session.session.id,
        parent_conversation_id: conversation.conversation.id,
    }
}

function MessageMatchedMemorySearch(
    conversation: root.retrieved_memory.RetrievedConversationGraph,
    message: root.retrieved_memory.RetrievedConversationMessageNode,
) -> bool {
    if (conversation.matched_message_ids.length() > 0) {
        conversation.matched_message_ids.includes(message.id)
    } else {
        true
    }
}

function IsCurrentSession(
    session: root.retrieved_memory.RetrievedSessionGraph,
    current_session_id: string?,
) -> bool {
    current_session_id != null && session.session.id == current_session_id
}
