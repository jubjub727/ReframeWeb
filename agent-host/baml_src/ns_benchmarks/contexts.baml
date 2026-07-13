function ConversationContext(
    conversation: BenchmarkConversation,
) -> root.turn_context.ConversationHistory {
    root.turn_context.ConversationHistory {
        id: conversation.id,
        name: conversation.name,
        created_at: conversation.created_at,
        updated_at: conversation.updated_at,
        read_at: conversation.read_at,
        messages: conversation
            .messages
            .map(
                (message) -> {
                    root.turn_context.ConversationHistoryMessage {
                        created_at: message.created_at,
                        updated_at: message.updated_at,
                        read_at: message.read_at,
                        role: message.role,
                        content: message.content,
                    }
                },
            ),
    }
}

function ConversationContexts(
    conversations: BenchmarkConversation[],
) -> root.turn_context.ConversationHistory[] {
    conversations
        .map(
            (conversation) -> {
                ConversationContext(conversation)
            },
        )
}

function SessionMemoryContexts(
    memories: BenchmarkMemory[],
) -> root.turn_context.SessionMemoryContext[] {
    memories
        .map(
            (memory) -> {
                root.turn_context.SessionMemoryContext {
                    title: memory.title,
                    description: memory.description,
                    tags: memory.tags,
                    created_at: memory.created_at,
                    updated_at: memory.updated_at,
                    read_at: memory.read_at,
                }
            },
        )
}

function UserPreferenceContexts(
    memories: BenchmarkMemory[],
) -> root.turn_context.UserPreferenceMemoryContext[] {
    memories
        .map(
            (memory) -> {
                root.turn_context.UserPreferenceMemoryContext {
                    id: `benchmark_preference:${memory.title}`,
                    title: memory.title,
                    description: memory.description,
                    tags: memory.tags,
                    created_at: memory.created_at,
                    updated_at: memory.updated_at,
                    read_at: memory.read_at,
                }
            },
        )
}

function AvailableTaskContexts(tasks: BenchmarkTask[]) -> root.task_catalog.AvailableTask[] {
    tasks
        .map(
            (task) -> {
                root.task_catalog.AvailableTask {
                    id: task.id,
                    name: task.name,
                    description: task.description,
                    input: task.input,
                    output: task.output,
                    prompt: task.prompt,
                    provider_id: task.provider_id,
                    created_at: task.created_at,
                    updated_at: task.updated_at,
                    read_at: task.read_at,
                }
            },
        )
}

function SelectedTaskContext(task: BenchmarkTask) -> root.task_catalog.SelectedTaskContext {
    root.task_catalog.SelectedTaskContext {
        id: task.id,
        name: task.name,
        description: task.description,
        input: task.input,
        output: task.output,
        prompt: task.prompt,
        provider_id: task.provider_id,
        created_at: task.created_at,
        updated_at: task.updated_at,
        read_at: task.read_at,
    }
}

function SelectedTaskForCase(
    case: ControlFlowBenchmarkCase,
    selected_task_id: string,
) -> root.task_catalog.SelectedTaskContext {
    root.task_catalog.SelectedTask(AvailableTaskContexts(case.available_tasks), selected_task_id)
}

function TaskChoiceMemoryContexts(
    memories: BenchmarkMemory[],
) -> root.task.TaskChoiceMemoryContext[] {
    memories
        .map(
            (memory) -> {
                root.task.TaskChoiceMemoryContext {
                    title: memory.title,
                    description: memory.description,
                    tags: memory.tags,
                    created_at: memory.created_at,
                    updated_at: memory.updated_at,
                    read_at: memory.read_at,
                }
            },
        )
}

function ConversationEvaluationMemoryContexts(
    memories: BenchmarkMemory[],
) -> root.memory.ConversationEvaluationMemoryContext[] {
    memories
        .map(
            (memory) -> {
                root.memory.ConversationEvaluationMemoryContext {
                    title: memory.title,
                    description: memory.description,
                    tags: memory.tags,
                    created_at: memory.created_at,
                    updated_at: memory.updated_at,
                    read_at: memory.read_at,
                }
            },
        )
}

function SearchDepthMemoryContexts(
    memories: BenchmarkMemory[],
) -> root.memory.SearchDepthMemoryContext[] {
    memories
        .map(
            (memory) -> {
                root.memory.SearchDepthMemoryContext {
                    title: memory.title,
                    description: memory.description,
                    tags: memory.tags,
                    created_at: memory.created_at,
                    updated_at: memory.updated_at,
                    read_at: memory.read_at,
                }
            },
        )
}

function TaskPromptConversation(
    case: TaskPromptBenchmarkCase,
    timestamp: string,
) -> root.turn_context.ConversationHistory {
    let messages = case
        .messages
        .map(
            (message) -> {
                root.turn_context.ConversationHistoryMessage {
                    created_at: timestamp,
                    updated_at: timestamp,
                    read_at: "NONE",
                    role: message.role,
                    content: message.content,
                }
            },
        );
    messages
        .push(
            root.turn_context.ConversationHistoryMessage {
                created_at: timestamp,
                updated_at: timestamp,
                read_at: "NONE",
                role: "human",
                content: case.current_user_request,
            },
        );
    root.turn_context.ConversationHistory {
        id: `benchmark_conversation:${case.id}`,
        name: case.conversation_name,
        created_at: timestamp,
        updated_at: timestamp,
        read_at: "NONE",
        messages: messages,
    }
}

function TaskPromptSessionMemoryContexts(
    case: TaskPromptBenchmarkCase,
    timestamp: string,
) -> root.turn_context.SessionMemoryContext[] {
    case.session_memories
        .map(
            (memory) -> {
                root.turn_context.SessionMemoryContext {
                    title: memory.title,
                    description: memory.description,
                    tags: memory.tags,
                    created_at: timestamp,
                    updated_at: timestamp,
                    read_at: "NONE",
                }
            },
        )
}

function TaskPromptSelectedMemoryContexts(
    case: TaskPromptBenchmarkCase,
    timestamp: string,
) -> root.task.TaskPromptSelectedMemoryContext[] {
    case.session_memories
        .map(
            (memory) -> {
                root.task.TaskPromptSelectedMemoryContext {
                    title: memory.title,
                    description: memory.description,
                    tags: memory.tags,
                    created_at: timestamp,
                    updated_at: timestamp,
                    read_at: "NONE",
                }
            },
        )
}

function MemoryRelevanceSelectedTask(
    case: ControlFlowBenchmarkCase,
) -> root.task_catalog.SelectedTaskContext {
    SelectedTaskForCase(case, case.expected_task_id)
}

function MemoryRelevanceCandidates(
    case: ControlFlowBenchmarkCase,
) -> root.memory.RetrievedMemoryCandidate[] {
    let session_candidates = case
        .session
        .memories
        .map(
            (memory) -> {
                root.memory.RetrievedMemoryCandidate {
                    id: `benchmark_memory:${case.id}:${memory.title}`,
                    kind: "current_session_memory",
                    title: memory.title,
                    description: memory.description,
                    tags: memory.tags,
                    created_at: memory.created_at,
                    updated_at: memory.updated_at,
                    read_at: memory.read_at,
                    retrieval_matched: true,
                    parent_session_id: case.session.id,
                    parent_conversation_id: null,
                }
            },
        );
    let preference_candidates = case
        .user_preferences
        .map(
            (memory) -> {
                root.memory.RetrievedMemoryCandidate {
                    id: `benchmark_preference:${case.id}:${memory.title}`,
                    kind: "user_preference",
                    title: memory.title,
                    description: memory.description,
                    tags: memory.tags,
                    created_at: memory.created_at,
                    updated_at: memory.updated_at,
                    read_at: memory.read_at,
                    retrieval_matched: true,
                    parent_session_id: null,
                    parent_conversation_id: null,
                }
            },
        );
    session_candidates.concat(preference_candidates)
}

function MemoryRelevanceExpectedIds(case: ControlFlowBenchmarkCase) -> string[] {
    case.session
        .memories
        .map(
            (memory) -> {
                `benchmark_memory:${case.id}:${memory.title}`
            },
        )
}
