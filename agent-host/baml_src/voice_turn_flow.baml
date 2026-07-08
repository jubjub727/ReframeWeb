class VoicePromptUnderstanding {
    task_choice: TaskChoiceDecision,
    selected_task: SelectedTaskContext,
    memory_search_hints: ConversationMemorySearchHints,
    search_depths: SearchDepthDecision,
    timings: VoicePromptUnderstandingTimings,
}

class VoicePromptContinuation {
    relevance_decision: RelevantMemoryDecision,
    selected_memories: RetrievedMemoryGraph,
    selected_memory_contexts: TaskPromptSelectedMemoryContext[],
    task_prompt: TaskPromptDecision,
    timings: VoicePromptContinuationTimings,
}

class VoicePromptUnderstandingTimings {
    task_choice_ms: bigint,
    memory_search_ms: bigint,
    search_depth_ms: bigint,
}

class VoicePromptContinuationTimings {
    memory_relevance_ms: bigint,
    task_prompt_ms: bigint,
}

function UnderstandVoicePrompt(
    current_timestamp: string,
    current_user_request: string,
    current_conversation: ConversationHistory?,
    session_memories: SessionMemoryContext[],
    user_preferences: UserPreferenceMemoryContext[],
    available_tasks: AvailableTask[],
    task_choice_memories: TaskChoiceMemoryContext[],
    conversation_evaluation_memories: ConversationEvaluationMemoryContext[],
    search_depth_memories: SearchDepthMemoryContext[],
    machine_state: MachineStateContext,
) -> VoicePromptUnderstanding {
    let task_choice_started_at = baml.time.Instant.now();
    let task_choice = ChooseTask(
        current_user_request,
        current_conversation,
        session_memories,
        user_preferences,
        available_tasks,
        task_choice_memories,
        machine_state,
    );
    let task_choice_ms = task_choice_started_at.elapsed().to_milliseconds();
    let selected_task = SelectedTaskDetails(available_tasks, task_choice.selected_task_id);
    let memory_search_started_at = baml.time.Instant.now();
    let memory_search_hints = ChooseMemorySearch(
        current_user_request,
        current_conversation,
        session_memories,
        selected_task,
        conversation_evaluation_memories,
        machine_state,
    );
    let memory_search_ms = memory_search_started_at.elapsed().to_milliseconds();
    let search_depth_started_at = baml.time.Instant.now();
    let search_depths = ChooseMemorySearchDepths(
        current_timestamp,
        current_user_request,
        current_conversation,
        session_memories,
        selected_task,
        memory_search_hints,
        MemorySearchDomains(),
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
    current_conversation: ConversationHistory?,
    session_memories: SessionMemoryContext[],
    selected_task: SelectedTaskContext,
    retrieved_memories: RetrievedMemoryGraph,
    current_session_id: string?,
    relevance_memories: RelevanceMemoryContext[],
    task_prompt_memories: TaskPromptMemoryContext[],
    machine_state: MachineStateContext,
) -> VoicePromptContinuation {
    let memory_relevance_started_at = baml.time.Instant.now();
    let relevance_decision = SelectRelevantMemories(
        current_user_request,
        current_conversation,
        session_memories,
        selected_task,
        MemoryCandidates(retrieved_memories, current_session_id),
        relevance_memories,
        machine_state,
    );
    let memory_relevance_ms = memory_relevance_started_at.elapsed().to_milliseconds();
    let selected_memories = RelevantMemoryGraph(retrieved_memories, relevance_decision);
    let selected_memory_contexts = TaskPromptMemoryContexts(selected_memories, relevance_decision.kept_memory_ids, current_session_id);
    let task_prompt_started_at = baml.time.Instant.now();
    let composition = ComposeTaskInput(
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
        task_prompt: FinishTaskPrompt(selected_task.prompt, composition),
        timings: VoicePromptContinuationTimings {
            memory_relevance_ms: memory_relevance_ms,
            task_prompt_ms: task_prompt_ms,
        },
    }
}
