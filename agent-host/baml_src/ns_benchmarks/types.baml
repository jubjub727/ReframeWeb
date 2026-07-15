class BenchmarkConversationMessage {
    created_at: string,
    updated_at: string,
    read_at: string,
    role: string,
    content: string,
}

class BenchmarkConversation {
    id: string,
    name: string,
    created_at: string,
    updated_at: string,
    read_at: string,
    messages: BenchmarkConversationMessage[],
}

class BenchmarkMemory {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class BenchmarkTask {
    id: string,
    name: string,
    description: string,
    input: string,
    output: string,
    prompt: string,
    provider_id: string,
    model_id: string,
    created_at: string,
    updated_at: string,
    read_at: string,
}

class BenchmarkSession {
    id: string,
    name: string,
    created_at: string,
    updated_at: string,
    read_at: string,
    conversations: BenchmarkConversation[],
    memories: BenchmarkMemory[],
}

class ControlFlowBenchmarkCase {
    id: string,
    current_timestamp: string,
    current_user_request: string,
    expected_task_id: string,
    available_tasks: BenchmarkTask[],
    session: BenchmarkSession,
    task_choice_memories: BenchmarkMemory[],
    user_preferences: BenchmarkMemory[],
    conversation_evaluation_memories: BenchmarkMemory[],
    search_depth_memories: BenchmarkMemory[],
    task_prompt_memories: BenchmarkMemory[],
}

class ConversationEvaluationBenchmarkCase {
    id: string,
    current_user_request: string,
    selected_task: BenchmarkTask,
    session_conversations: BenchmarkConversation[],
    session_memories: BenchmarkMemory[],
    conversation_evaluation_memories: BenchmarkMemory[],
    review_focus: string,
}

class TaskChoiceBenchmarkCase {
    id: string,
    transcript: string,
    expected_task_name: string,
}

class TaskPromptCaseMessage {
    role: string,
    content: string,
}

class TaskPromptCaseMemory {
    title: string,
    description: string,
    tags: string[],
}

class TaskPromptBenchmarkCase {
    id: string,
    current_user_request: string,
    expected_task_name: string,
    conversation_name: string,
    messages: TaskPromptCaseMessage[],
    session_memories: TaskPromptCaseMemory[],
}
