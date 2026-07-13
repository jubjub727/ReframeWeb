function Candidates(
    memories: root.memory.RetrievedMemoryGraph,
    current_session_id: string?,
    user_preferences: root.turn_context.UserPreferenceMemoryContext[],
) -> root.memory.RetrievedMemoryCandidate[] {
    let candidates: root.memory.RetrievedMemoryCandidate[] = [];

    for (let task in memories.task_catalog) {
        let _ = candidates.push(TaskCandidate(task));
    }
    for (let memory in memories.current_session_memories) {
        let _ = candidates.push(CurrentSessionMemoryCandidate(memory, current_session_id));
    }
    for (let preference in user_preferences) {
        let _ = candidates.push(UserPreferenceCandidate(preference));
    }
    for (let session in memories.past_sessions) {
        let is_current_session = IsCurrentSession(session, current_session_id);
        let _ = candidates.push(SessionCandidate(session, is_current_session));
        for (let memory in session.session_memories) {
            let _ = candidates.push(SessionMemoryCandidate(session, memory, is_current_session));
        }
        for (let conversation in session.conversations) {
            let _ = candidates.push(ConversationCandidate(session, conversation, is_current_session));
            for (let message in conversation.messages) {
                let _ = candidates
                    .push(
                        ConversationMessageCandidate(session, conversation, message, is_current_session),
                    );
            }
        }
    }

    candidates
}

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
