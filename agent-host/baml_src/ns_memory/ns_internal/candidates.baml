function TaskCandidate(
    task: root.memory.RetrievedTaskNode,
) -> root.memory.RetrievedMemoryCandidate {
    root.memory.RetrievedMemoryCandidate {
        id: task.id,
        kind: "task",
        title: task.name,
        description: TaskCandidateDescription(task),
        tags: task.tags,
        created_at: task.created_at,
        updated_at: task.updated_at,
        read_at: task.read_at,
        retrieval_matched: true,
        parent_session_id: null,
        parent_conversation_id: null,
    }
}

function CurrentSessionMemoryCandidate(
    memory: root.memory.RetrievedSessionMemoryNode,
    current_session_id: string?,
) -> root.memory.RetrievedMemoryCandidate {
    root.memory.RetrievedMemoryCandidate {
        id: memory.id,
        kind: "current_session_memory",
        title: memory.title,
        description: memory.description,
        tags: memory.tags,
        created_at: memory.created_at,
        updated_at: memory.updated_at,
        read_at: memory.read_at,
        retrieval_matched: false,
        parent_session_id: current_session_id,
        parent_conversation_id: null,
    }
}

function UserPreferenceCandidate(
    preference: root.turn_context.UserPreferenceMemoryContext,
) -> root.memory.RetrievedMemoryCandidate {
    root.memory.RetrievedMemoryCandidate {
        id: preference.id,
        kind: "user_preference",
        title: preference.title,
        description: preference.description,
        tags: preference.tags,
        created_at: preference.created_at,
        updated_at: preference.updated_at,
        read_at: preference.read_at,
        retrieval_matched: false,
        parent_session_id: null,
        parent_conversation_id: null,
    }
}

function TaskCandidateDescription(task: root.memory.RetrievedTaskNode) -> string {
    let pieces: string[] = [];
    if (task.description != "") {
        let _ = pieces.push(`description: ${task.description}`);
    }
    if (task.input != "") {
        let _ = pieces.push(`input: ${task.input}`);
    }
    if (task.output != "") {
        let _ = pieces.push(`output: ${task.output}`);
    }
    if (task.prompt != "") {
        let _ = pieces.push(`prompt: ${task.prompt}`);
    }
    if (task.provider_id != "") {
        let _ = pieces.push(`provider_id: ${task.provider_id}`);
    }
    pieces.join("\n")
}

function SessionCandidate(
    session: root.memory.RetrievedSessionGraph,
    is_current_session: bool,
) -> root.memory.RetrievedMemoryCandidate {
    root.memory.RetrievedMemoryCandidate {
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
    session: root.memory.RetrievedSessionGraph,
    memory: root.memory.RetrievedSessionMemoryNode,
    is_current_session: bool,
) -> root.memory.RetrievedMemoryCandidate {
    root.memory.RetrievedMemoryCandidate {
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
    session: root.memory.RetrievedSessionGraph,
    conversation: root.memory.RetrievedConversationGraph,
    is_current_session: bool,
) -> root.memory.RetrievedMemoryCandidate {
    root.memory.RetrievedMemoryCandidate {
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
    session: root.memory.RetrievedSessionGraph,
    conversation: root.memory.RetrievedConversationGraph,
    message: root.memory.RetrievedConversationMessageNode,
    is_current_session: bool,
) -> root.memory.RetrievedMemoryCandidate {
    root.memory.RetrievedMemoryCandidate {
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
    conversation: root.memory.RetrievedConversationGraph,
    message: root.memory.RetrievedConversationMessageNode,
) -> bool {
    let has_explicit_matches = conversation.matched_message_ids.length() > 0;
    if (has_explicit_matches) {
        conversation.matched_message_ids.includes(message.id)
    } else {
        true
    }
}

function IsCurrentSession(
    session: root.memory.RetrievedSessionGraph,
    current_session_id: string?,
) -> bool {
    current_session_id != null && session.session.id == current_session_id
}
