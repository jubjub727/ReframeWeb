//# Build candidates

function Candidates(
    memories: root.memory.RetrievedMemoryGraph,
    current_session_id: string?,
    user_preferences: root.turn_context.UserPreferenceMemoryContext[],
) -> root.memory.RetrievedMemoryCandidate[] {
    let candidates: root.memory.RetrievedMemoryCandidate[] = [];

    for (let task in memories.task_catalog) {
        let _ = candidates.push(root.memory.internal.TaskCandidate(task));
    }
    for (let memory in memories.current_session_memories) {
        let _ = candidates
            .push(root.memory.internal.CurrentSessionMemoryCandidate(memory, current_session_id));
    }
    for (let preference in user_preferences) {
        let _ = candidates.push(root.memory.internal.UserPreferenceCandidate(preference));
    }

    for (let session in memories.past_sessions) {
        let is_current_session = root.memory.internal.IsCurrentSession(session, current_session_id);
        let _ = candidates.push(root.memory.internal.SessionCandidate(session, is_current_session));
        for (let memory in session.session_memories) {
            let _ = candidates
                .push(
                    root.memory.internal.SessionMemoryCandidate(session, memory, is_current_session),
                );
        }
        for (let conversation in session.conversations) {
            let _ = candidates
                .push(
                    root.memory
                        .internal
                        .ConversationCandidate(session, conversation, is_current_session),
                );
            for (let message in conversation.messages) {
                let _ = candidates
                    .push(
                        root.memory
                            .internal
                            .ConversationMessageCandidate(
                                session,
                                conversation,
                                message,
                                is_current_session,
                            ),
                    );
            }
        }
    }

    candidates
}
