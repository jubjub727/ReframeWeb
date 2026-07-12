function UnderstandVoicePrompt(
    current_timestamp: string,
    current_user_request: string,
    current_conversation: root.context.ConversationHistory?,
    session_memories: root.context.SessionMemoryContext[],
    user_preferences: root.context.UserPreferenceMemoryContext[],
    available_tasks: root.task_routing.AvailableTask[],
    task_choice_memories: root.task_routing.TaskChoiceMemoryContext[],
    conversation_evaluation_memories: root.memory_search.ConversationEvaluationMemoryContext[],
    search_depth_memories: root.memory_search.SearchDepthMemoryContext[],
    machine_state: root.context.MachineStateContext,
) -> VoicePromptUnderstanding {
    let task_choice_started_at = baml.time.Instant.now();
    let task_choice = root
        .task_routing
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
    let selected_task = root.task_routing.SelectedTask(available_tasks, task_choice.selected_task_id);
    let memory_search_started_at = baml.time.Instant.now();
    let memory_search_hints = root
        .memory_search
        .ChooseMemorySearch(
            current_user_request,
            current_conversation,
            session_memories,
            selected_task,
            conversation_evaluation_memories,
            machine_state,
        );
    let memory_search_ms = memory_search_started_at.elapsed().to_milliseconds();
    let search_depth_started_at = baml.time.Instant.now();
    let search_depths = root
        .memory_search
        .ChooseMemorySearchDepths(
            current_timestamp,
            current_user_request,
            current_conversation,
            session_memories,
            selected_task,
            memory_search_hints,
            root.memory_search.SearchDomains(),
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

function ContinueVoicePrompt(
    current_user_request: string,
    current_conversation: root.context.ConversationHistory?,
    session_memories: root.context.SessionMemoryContext[],
    user_preferences: root.context.UserPreferenceMemoryContext[],
    selected_task: root.task_routing.SelectedTaskContext,
    retrieved_memories: root.retrieved_memory.RetrievedMemoryGraph,
    current_session_id: string?,
    relevance_memories: root.memory_selection.RelevanceMemoryContext[],
    task_prompt_memories: root.task_prompt.TaskPromptMemoryContext[],
    machine_state: root.context.MachineStateContext,
) -> VoicePromptContinuation {
    let memory_relevance_started_at = baml.time.Instant.now();
    let relevance_decision = root
        .memory_selection
        .SelectRelevantMemories(
            current_user_request,
            current_conversation,
            session_memories,
            selected_task,
            root.memory_selection
                .Candidates(retrieved_memories, current_session_id, user_preferences),
            relevance_memories,
            machine_state,
        );
    let memory_relevance_ms = memory_relevance_started_at.elapsed().to_milliseconds();
    let selected_memories = root.memory_selection.SelectedGraph(retrieved_memories, relevance_decision);
    let selected_memory_contexts = root
        .task_prompt
        .PromptContexts(
            selected_memories,
            relevance_decision.kept_memory_ids,
            current_session_id,
            user_preferences,
        );
    let task_prompt_started_at = baml.time.Instant.now();
    let composition = root
        .task_prompt
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
        task_prompt: root.task_prompt.PromptDecision(selected_task.prompt, composition),
        timings: VoicePromptContinuationTimings {
            memory_relevance_ms: memory_relevance_ms,
            task_prompt_ms: task_prompt_ms,
        },
    }
}
