//# Build context

function PromptContexts(
    memories: root.memory.RetrievedMemoryGraph,
    selected_memory_ids: string[],
    current_session_id: string?,
    user_preferences: root.turn_context.UserPreferenceMemoryContext[],
) -> root.task.TaskPromptSelectedMemoryContext[] {
    let contexts: root.task.TaskPromptSelectedMemoryContext[] = [];

    for (let task in memories.task_catalog) {
        let _ = contexts.push(root.task.internal.ContextFromTask(task));
    }
    for (let memory in memories.current_session_memories) {
        let _ = contexts.push(root.task.internal.ContextFromSessionMemory(memory));
    }
    for (let preference in user_preferences) {
        if (selected_memory_ids.includes(preference.id)) {
            let _ = contexts.push(root.task.internal.ContextFromUserPreference(preference));
        }
    }

    for (let session in memories.past_sessions) {
        let is_current_session = root.memory.internal.IsCurrentSession(session, current_session_id);
        if (root.task.internal.KeepSessionContext(session, selected_memory_ids)) {
            let _ = contexts.push(root.task.internal.ContextFromSession(session, is_current_session));
        }
        for (let memory in session.session_memories) {
            let _ = contexts.push(root.task.internal.ContextFromSessionMemory(memory));
        }
        for (let conversation in session.conversations) {
            if (root.task.internal.KeepConversationContext(conversation, selected_memory_ids)) {
                let _ = contexts
                    .push(
                        root.task
                            .internal
                            .ContextFromConversation(session, conversation, is_current_session),
                    );
            }
            for (let message in conversation.messages) {
                let _ = contexts.push(root.task.internal.ContextFromMessage(message));
            }
        }
    }

    contexts
}
