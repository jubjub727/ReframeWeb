function ContextFromTask(
    task: root.memory.RetrievedTaskNode,
) -> root.task.TaskPromptSelectedMemoryContext {
    root.task.TaskPromptSelectedMemoryContext {
        title: task.name,
        description: task.description,
        tags: task.tags,
        created_at: task.created_at,
        updated_at: task.updated_at,
        read_at: task.read_at,
    }
}

function ContextFromSession(
    session: root.memory.RetrievedSessionGraph,
    is_current_session: bool,
) -> root.task.TaskPromptSelectedMemoryContext {
    root.task.TaskPromptSelectedMemoryContext {
        title: `${if (is_current_session) { "Current" } else { "Past" }} session: ${session.session.name}`,
        description: "Parent session for selected remembered context.",
        tags: session.session.tags,
        created_at: session.session.created_at,
        updated_at: session.session.updated_at,
        read_at: session.session.read_at,
    }
}

function ContextFromConversation(
    session: root.memory.RetrievedSessionGraph,
    conversation: root.memory.RetrievedConversationGraph,
    is_current_session: bool,
) -> root.task.TaskPromptSelectedMemoryContext {
    root.task.TaskPromptSelectedMemoryContext {
        title: `${if (is_current_session) { "Current" } else { "Past" }} conversation: ${conversation.conversation.name}`,
        description: `Parent conversation for selected remembered context in session: ${session.session.name}.`,
        tags: conversation.conversation.tags,
        created_at: conversation.conversation.created_at,
        updated_at: conversation.conversation.updated_at,
        read_at: conversation.conversation.read_at,
    }
}

function ContextFromSessionMemory(
    memory: root.memory.RetrievedSessionMemoryNode,
) -> root.task.TaskPromptSelectedMemoryContext {
    root.task.TaskPromptSelectedMemoryContext {
        title: memory.title,
        description: memory.description,
        tags: memory.tags,
        created_at: memory.created_at,
        updated_at: memory.updated_at,
        read_at: memory.read_at,
    }
}

function ContextFromUserPreference(
    preference: root.turn_context.UserPreferenceMemoryContext,
) -> root.task.TaskPromptSelectedMemoryContext {
    root.task.TaskPromptSelectedMemoryContext {
        title: preference.title,
        description: preference.description,
        tags: preference.tags,
        created_at: preference.created_at,
        updated_at: preference.updated_at,
        read_at: preference.read_at,
    }
}

function ContextFromMessage(
    message: root.memory.RetrievedConversationMessageNode,
) -> root.task.TaskPromptSelectedMemoryContext {
    root.task.TaskPromptSelectedMemoryContext {
        title: `${message.role} message`,
        description: message.content,
        tags: message.tags,
        created_at: message.created_at,
        updated_at: message.updated_at,
        read_at: message.read_at,
    }
}

function KeepSessionContext(
    session: root.memory.RetrievedSessionGraph,
    selected_ids: string[],
) -> bool {
    session.matched
        || selected_ids.includes(session.session.id)
        || session.session_memories.length() > 0
        || session.conversations.length() > 0
}

function KeepConversationContext(
    conversation: root.memory.RetrievedConversationGraph,
    selected_ids: string[],
) -> bool {
    conversation.matched
        || selected_ids.includes(conversation.conversation.id)
        || conversation.messages.length() > 0
}
