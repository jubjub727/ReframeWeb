//# Plan voice turn

function UnderstandVoicePrompt(
    current_timestamp: string,
    current_user_request: string,
    current_conversation: root.turn_context.ConversationHistory?,
    session_memories: root.turn_context.SessionMemoryContext[],
    user_preferences: root.turn_context.UserPreferenceMemoryContext[],
    available_tasks: root.task_catalog.AvailableTask[],
    task_choice_memories: root.task.TaskChoiceMemoryContext[],
    conversation_evaluation_memories: root.memory.ConversationEvaluationMemoryContext[],
    search_depth_memories: root.memory.SearchDepthMemoryContext[],
    machine_state: root.turn_context.MachineStateContext,
) -> VoicePromptUnderstanding {
    //# Choose task
    let task_choice_started_at = baml.time.Instant.now();
    let task_choice = root
        .task
        .ChooseTask(
            current_user_request,
            current_conversation,
            session_memories,
            user_preferences,
            available_tasks,
            task_choice_memories,
            machine_state,
        );
    let task_choice_ms = task_choice_started_at.elapsed().to_milliseconds();
    let selected_task = root.task_catalog.SelectedTask(available_tasks, task_choice.selected_task_id);
    //# Plan memory search
    let memory_search_started_at = baml.time.Instant.now();
    let memory_search_hints = root
        .memory
        .ChooseMemorySearch(
            current_user_request,
            current_conversation,
            session_memories,
            selected_task,
            conversation_evaluation_memories,
            machine_state,
        );
    let memory_search_ms = memory_search_started_at.elapsed().to_milliseconds();
    //# Set search depth
    let search_depth_started_at = baml.time.Instant.now();
    let search_depths = root
        .memory
        .ChooseMemorySearchDepths(
            current_timestamp,
            current_user_request,
            current_conversation,
            session_memories,
            selected_task,
            memory_search_hints,
            root.memory.SearchDomains(),
            search_depth_memories,
            machine_state,
        );
    let search_depth_ms = search_depth_started_at.elapsed().to_milliseconds();
    VoicePromptUnderstanding {
        task_choice: task_choice,
        selected_task: selected_task,
        memory_search_hints: memory_search_hints,
        search_depths: search_depths,
        timings: VoicePromptUnderstandingTimings {
            task_choice_ms: task_choice_ms,
            memory_search_ms: memory_search_ms,
            search_depth_ms: search_depth_ms,
        },
    }
}

//# Build voice prompt

function ContinueVoicePrompt(
    current_user_request: string,
    current_conversation: root.turn_context.ConversationHistory?,
    session_memories: root.turn_context.SessionMemoryContext[],
    user_preferences: root.turn_context.UserPreferenceMemoryContext[],
    selected_task: root.task_catalog.SelectedTaskContext,
    retrieved_memories: root.memory.RetrievedMemoryGraph,
    current_session_id: string?,
    relevance_memories: root.memory.RelevanceMemoryContext[],
    task_prompt_memories: root.task.TaskPromptMemoryContext[],
    machine_state: root.turn_context.MachineStateContext,
) -> VoicePromptContinuation {
    //# Select memory
    let memory_relevance_started_at = baml.time.Instant.now();
    let relevance_decision = root
        .memory
        .SelectRelevantMemories(
            current_user_request,
            current_conversation,
            session_memories,
            selected_task,
            root.memory.Candidates(retrieved_memories, current_session_id, user_preferences),
            relevance_memories,
            machine_state,
        );
    let memory_relevance_ms = memory_relevance_started_at.elapsed().to_milliseconds();
    let selected_memories = root.memory.SelectedGraph(retrieved_memories, relevance_decision);
    let selected_memory_contexts = root
        .task
        .PromptContexts(
            selected_memories,
            relevance_decision.kept_memory_ids,
            current_session_id,
            user_preferences,
        );
    //# Compose handoff
    let task_prompt_started_at = baml.time.Instant.now();
    let composition = root
        .task
        .ComposeTaskInput(
            current_user_request,
            current_conversation,
            session_memories,
            selected_task,
            selected_memory_contexts,
            task_prompt_memories,
            machine_state,
        );
    let task_prompt_ms = task_prompt_started_at.elapsed().to_milliseconds();
    VoicePromptContinuation {
        relevance_decision: relevance_decision,
        selected_memories: selected_memories,
        selected_memory_contexts: selected_memory_contexts,
        task_prompt: root.task.PromptDecision(selected_task.prompt, composition),
        timings: VoicePromptContinuationTimings {
            memory_relevance_ms: memory_relevance_ms,
            task_prompt_ms: task_prompt_ms,
        },
    }
}
