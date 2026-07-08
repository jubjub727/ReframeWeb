class RetrievedTaskNode {
    id: string,
    name: string,
    description: string,
    input: string,
    output: string,
    prompt: string,
    provider_id: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RetrievedSessionNode {
    id: string,
    name: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RetrievedSessionMemoryNode {
    id: string,
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RetrievedConversationNode {
    id: string,
    name: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RetrievedConversationMessageNode {
    id: string,
    role: string,
    content: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RetrievedConversationGraph {
    conversation: RetrievedConversationNode,
    matched: bool,
    messages: RetrievedConversationMessageNode[],
    matched_message_ids: string[],
}

class RetrievedSessionGraph {
    session: RetrievedSessionNode,
    matched: bool,
    conversations: RetrievedConversationGraph[],
    session_memories: RetrievedSessionMemoryNode[],
}

class RetrievedMemoryGraph {
    task_catalog: RetrievedTaskNode[],
    past_sessions: RetrievedSessionGraph[],
    current_session_memories: RetrievedSessionMemoryNode[],
}

function MemoryCandidates(
    memories: RetrievedMemoryGraph,
    current_session_id: string?,
    user_preferences: UserPreferenceMemoryContext[],
) -> RetrievedMemoryCandidate[] {
    let candidates: RetrievedMemoryCandidate[] = [];

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

function RelevantMemoryGraph(
    memories: RetrievedMemoryGraph,
    decision: RelevantMemoryDecision,
) -> RetrievedMemoryGraph {
    let kept_ids = decision.kept_memory_ids;
    let sessions: RetrievedSessionGraph[] = [];

    for (let session in memories.past_sessions) {
        if let filtered: RetrievedSessionGraph = RelevantSessionGraph(session, kept_ids) {
            let _ = sessions.push(filtered);
        }
    }

    RetrievedMemoryGraph {
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

function TaskPromptMemoryContexts(
    memories: RetrievedMemoryGraph,
    selected_memory_ids: string[],
    current_session_id: string?,
    user_preferences: UserPreferenceMemoryContext[],
) -> TaskPromptSelectedMemoryContext[] {
    let contexts: TaskPromptSelectedMemoryContext[] = [];

    for (let task in memories.task_catalog) {
        let _ = contexts.push(TaskPromptContextFromTask(task));
    }

    for (let memory in memories.current_session_memories) {
        let _ = contexts.push(TaskPromptContextFromSessionMemory(memory));
    }

    for (let preference in user_preferences) {
        if (selected_memory_ids.includes(preference.id)) {
            let _ = contexts.push(TaskPromptContextFromUserPreference(preference));
        }
    }

    for (let session in memories.past_sessions) {
        let is_current_session = IsCurrentSession(session, current_session_id);
        if (KeepSessionContextForPrompt(session, selected_memory_ids)) {
            let _ = contexts.push(TaskPromptContextFromSession(session, is_current_session));
        }
        for (let memory in session.session_memories) {
            let _ = contexts.push(TaskPromptContextFromSessionMemory(memory));
        }
        for (let conversation in session.conversations) {
            if (KeepConversationContextForPrompt(conversation, selected_memory_ids)) {
                let _ = contexts
                    .push(
                        TaskPromptContextFromConversation(session, conversation, is_current_session),
                    );
            }
            for (let message in conversation.messages) {
                let _ = contexts.push(TaskPromptContextFromMessage(message));
            }
        }
    }

    contexts
}

function RelevantSessionGraph(
    session: RetrievedSessionGraph,
    kept_ids: string[],
) -> RetrievedSessionGraph? {
    let conversations: RetrievedConversationGraph[] = [];
    for (let conversation in session.conversations) {
        if let filtered: RetrievedConversationGraph = RelevantConversationGraph(conversation, kept_ids) {
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
        RetrievedSessionGraph {
            session: session.session,
            matched: session.matched,
            conversations: conversations,
            session_memories: session_memories,
        }
    }
}

function RelevantConversationGraph(
    conversation: RetrievedConversationGraph,
    kept_ids: string[],
) -> RetrievedConversationGraph? {
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
        RetrievedConversationGraph {
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

function TaskCandidate(task: RetrievedTaskNode) -> RetrievedMemoryCandidate {
    RetrievedMemoryCandidate {
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
    memory: RetrievedSessionMemoryNode,
    current_session_id: string?,
) -> RetrievedMemoryCandidate {
    RetrievedMemoryCandidate {
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

function UserPreferenceCandidate(preference: UserPreferenceMemoryContext) -> RetrievedMemoryCandidate {
    RetrievedMemoryCandidate {
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

function SessionCandidate(
    session: RetrievedSessionGraph,
    is_current_session: bool,
) -> RetrievedMemoryCandidate {
    RetrievedMemoryCandidate {
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
    session: RetrievedSessionGraph,
    memory: RetrievedSessionMemoryNode,
    is_current_session: bool,
) -> RetrievedMemoryCandidate {
    RetrievedMemoryCandidate {
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
    session: RetrievedSessionGraph,
    conversation: RetrievedConversationGraph,
    is_current_session: bool,
) -> RetrievedMemoryCandidate {
    RetrievedMemoryCandidate {
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
    session: RetrievedSessionGraph,
    conversation: RetrievedConversationGraph,
    message: RetrievedConversationMessageNode,
    is_current_session: bool,
) -> RetrievedMemoryCandidate {
    RetrievedMemoryCandidate {
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

function TaskPromptContextFromTask(task: RetrievedTaskNode) -> TaskPromptSelectedMemoryContext {
    TaskPromptSelectedMemoryContext {
        title: task.name,
        description: task.description,
        tags: task.tags,
        created_at: task.created_at,
        updated_at: task.updated_at,
        read_at: task.read_at,
    }
}

function TaskPromptContextFromSession(
    session: RetrievedSessionGraph,
    is_current_session: bool,
) -> TaskPromptSelectedMemoryContext {
    TaskPromptSelectedMemoryContext {
        title: `${if (is_current_session) { "Current" } else { "Past" }} session: ${session.session.name}`,
        description: "Parent session for selected remembered context.",
        tags: session.session.tags,
        created_at: session.session.created_at,
        updated_at: session.session.updated_at,
        read_at: session.session.read_at,
    }
}

function TaskPromptContextFromConversation(
    session: RetrievedSessionGraph,
    conversation: RetrievedConversationGraph,
    is_current_session: bool,
) -> TaskPromptSelectedMemoryContext {
    TaskPromptSelectedMemoryContext {
        title: `${if (is_current_session) { "Current" } else { "Past" }} conversation: ${conversation.conversation.name}`,
        description: `Parent conversation for selected remembered context in session: ${session.session.name}.`,
        tags: conversation.conversation.tags,
        created_at: conversation.conversation.created_at,
        updated_at: conversation.conversation.updated_at,
        read_at: conversation.conversation.read_at,
    }
}

function TaskPromptContextFromSessionMemory(
    memory: RetrievedSessionMemoryNode,
) -> TaskPromptSelectedMemoryContext {
    TaskPromptSelectedMemoryContext {
        title: memory.title,
        description: memory.description,
        tags: memory.tags,
        created_at: memory.created_at,
        updated_at: memory.updated_at,
        read_at: memory.read_at,
    }
}

function TaskPromptContextFromUserPreference(
    preference: UserPreferenceMemoryContext,
) -> TaskPromptSelectedMemoryContext {
    TaskPromptSelectedMemoryContext {
        title: preference.title,
        description: preference.description,
        tags: preference.tags,
        created_at: preference.created_at,
        updated_at: preference.updated_at,
        read_at: preference.read_at,
    }
}

function TaskPromptContextFromMessage(
    message: RetrievedConversationMessageNode,
) -> TaskPromptSelectedMemoryContext {
    TaskPromptSelectedMemoryContext {
        title: `${message.role} message`,
        description: message.content,
        tags: message.tags,
        created_at: message.created_at,
        updated_at: message.updated_at,
        read_at: message.read_at,
    }
}

function TaskCandidateDescription(task: RetrievedTaskNode) -> string {
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

function MessageMatchedMemorySearch(
    conversation: RetrievedConversationGraph,
    message: RetrievedConversationMessageNode,
) -> bool {
    if (conversation.matched_message_ids.length() > 0) {
        conversation.matched_message_ids.includes(message.id)
    } else {
        true
    }
}

function KeepSessionContextForPrompt(
    session: RetrievedSessionGraph,
    selected_ids: string[],
) -> bool {
    session.matched
        || selected_ids.includes(session.session.id)
        || session.session_memories.length() > 0
        || session.conversations.length() > 0
}

function KeepConversationContextForPrompt(
    conversation: RetrievedConversationGraph,
    selected_ids: string[],
) -> bool {
    conversation.matched
        || selected_ids.includes(conversation.conversation.id)
        || conversation.messages.length() > 0
}

function IsCurrentSession(session: RetrievedSessionGraph, current_session_id: string?) -> bool {
    current_session_id != null && session.session.id == current_session_id
}
