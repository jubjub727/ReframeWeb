function ConversationContext(
    conversation: BenchmarkConversation,
) -> root.context.ConversationHistory {
    root.context.ConversationHistory {
        id: conversation.id,
        name: conversation.name,
        created_at: conversation.created_at,
        updated_at: conversation.updated_at,
        read_at: conversation.read_at,
        messages: conversation
            .messages
            .map(
                (message) -> {
                    root.context.ConversationHistoryMessage {
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
) -> root.context.ConversationHistory[] {
    conversations
        .map(
            (conversation) -> {
                ConversationContext(conversation)
            },
        )
}

function SessionMemoryContexts(memories: BenchmarkMemory[]) -> root.context.SessionMemoryContext[] {
    memories
        .map(
            (memory) -> {
                root.context.SessionMemoryContext {
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
) -> root.context.UserPreferenceMemoryContext[] {
    memories
        .map(
            (memory) -> {
                root.context.UserPreferenceMemoryContext {
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

function AvailableTaskContexts(tasks: BenchmarkTask[]) -> root.task_routing.AvailableTask[] {
    tasks
        .map(
            (task) -> {
                root.task_routing.AvailableTask {
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

function SelectedTaskContext(task: BenchmarkTask) -> root.task_routing.SelectedTaskContext {
    root.task_routing.SelectedTaskContext {
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
) -> root.task_routing.SelectedTaskContext {
    root.task_routing.SelectedTask(AvailableTaskContexts(case.available_tasks), selected_task_id)
}

function TaskChoiceMemoryContexts(
    memories: BenchmarkMemory[],
) -> root.task_routing.TaskChoiceMemoryContext[] {
    memories
        .map(
            (memory) -> {
                root.task_routing.TaskChoiceMemoryContext {
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
) -> root.memory_search.ConversationEvaluationMemoryContext[] {
    memories
        .map(
            (memory) -> {
                root.memory_search.ConversationEvaluationMemoryContext {
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
) -> root.memory_search.SearchDepthMemoryContext[] {
    memories
        .map(
            (memory) -> {
                root.memory_search.SearchDepthMemoryContext {
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
) -> root.context.ConversationHistory {
    let messages = case
        .messages
        .map(
            (message) -> {
                root.context.ConversationHistoryMessage {
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
            root.context.ConversationHistoryMessage {
                created_at: timestamp,
                updated_at: timestamp,
                read_at: "NONE",
                role: "human",
                content: case.current_user_request,
            },
        );
    root.context.ConversationHistory {
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
) -> root.context.SessionMemoryContext[] {
    case.session_memories
        .map(
            (memory) -> {
                root.context.SessionMemoryContext {
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
) -> root.task_prompt.TaskPromptSelectedMemoryContext[] {
    case.session_memories
        .map(
            (memory) -> {
                root.task_prompt.TaskPromptSelectedMemoryContext {
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
) -> root.task_routing.SelectedTaskContext {
    SelectedTaskForCase(case, case.expected_task_id)
}

function MemoryRelevanceCandidates(
    case: ControlFlowBenchmarkCase,
) -> root.memory_selection.RetrievedMemoryCandidate[] {
    let session_candidates = case
        .session
        .memories
        .map(
            (memory) -> {
                root.memory_selection.RetrievedMemoryCandidate {
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
                root.memory_selection.RetrievedMemoryCandidate {
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
