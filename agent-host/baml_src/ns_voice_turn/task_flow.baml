//# Run complete voice turn

function RunVoiceTurn(
    current_user_request: string,
    load_context: () -> VoiceTaskFlowContext,
    load_request_conversation: () -> root.turn_context.ConversationHistory?,
    load_task_conversation_scope: () -> VoiceTaskConversationScope,
    report_task_choice: (
        string,
        root.task.TaskChoiceDecision,
        root.task_catalog.SelectedTaskContext,
        bigint,
    ) -> bool,
    retrieve_memories: (string, VoicePromptUnderstanding) -> root.memory.RetrievedMemoryGraph,
    execute_task: (
        string,
        root.task.TaskChoiceDecision,
        string,
        VoicePromptContinuation,
    ) -> VoiceTaskExecutionBoundaryResult,
    dispatch_task_outputs: (string) -> bool,
    summarize_task_actions: (string, root.task.TaskChoiceDecision) -> string?,
    record_validation_reply: (string, string) -> bool,
    write_candidate_memories: (root.memory.CandidateMemoryWriteBatch) -> bool,
) -> VoiceTaskRunResult {
    let task_completion_ms = 0n;
    let completion_reviews: VoiceTaskCompletionReview[] = [];
    let failure_reviews: VoiceTaskFailureReview[] = [];
    let successful_tasks: SuccessfulVoiceTaskResult[] = [];
    let candidate_memories = root.memory.EmptyCandidateMemoryGroups();
    let consecutive_no_action_count = 0;
    let completed_tasks: CompletedVoiceTaskCycle[] = [];
    let request_result: VoiceRequestResultState = PendingVoiceRequestResult {  };
    let completion_context: VoiceTaskFlowContext? = null;
    let voice_request_complete = false;
    //# Task selection
    while (!voice_request_complete) {
        let cycle_finished = false;
        let cycle_result: VoiceRequestResultState = PendingVoiceRequestResult {  };
        //# Load context
        let context = load_context();
        completion_context = context;
        //# Choose task
        let task_choice_started_at = baml.time.Instant.now();
        let task_choice = root
            .task
            .ChooseTask(
                current_user_request,
                context.current_conversation,
                context.session_memories,
                context.user_preferences,
                context.available_tasks,
                context.task_choice_memories,
                context.machine_state,
            );
        let task_choice_ms = task_choice_started_at.elapsed().to_milliseconds();
        let selected_task = root.task_catalog.SelectedTask(context.available_tasks, task_choice.selected_task_id);
        //# Report task choice
        let _ = report_task_choice(context.cycle_id, task_choice, selected_task, task_choice_ms);
        root.memory
            .AddCandidateMemory(
                candidate_memories,
                root.memory.CandidateMemoryLayer.TASK_CHOICE,
                task_choice.candidate_memory,
            );
        consecutive_no_action_count
            = NextConsecutiveNoActionCount(selected_task, consecutive_no_action_count);
        if (selected_task.model_id == "magic:do-nothing") {
            //# Record no action
            cycle_finished = true;
            cycle_result
                = VoiceRequestResultAfterNoAction(
                    completed_tasks,
                    VoiceTaskNoActionResult {
                        cycle_id: context.cycle_id,
                        task_choice: task_choice,
                        selected_task: selected_task,
                        task_choice_ms: task_choice_ms,
                    },
                    task_completion_ms,
                    completion_reviews,
                    failure_reviews,
                );
        } else {
            //# Run selected task
            let task_conversation_scope = load_task_conversation_scope();
            let task_conversation = TaskConversation(context.current_conversation, task_conversation_scope);
            //# Plan memory search
            let memory_search_started_at = baml.time.Instant.now();
            let memory_search_hints = root
                .memory
                .ChooseMemorySearch(
                    current_user_request,
                    task_conversation,
                    context.session_memories,
                    selected_task,
                    context.conversation_evaluation_memories,
                    context.machine_state,
                );
            let memory_search_ms = memory_search_started_at.elapsed().to_milliseconds();
            root.memory
                .AddCandidateMemory(
                    candidate_memories,
                    root.memory.CandidateMemoryLayer.CONVERSATION_EVALUATION,
                    memory_search_hints.candidate_memory,
                );
            //# Set search depth
            let search_depth_started_at = baml.time.Instant.now();
            let search_depths = root
                .memory
                .ChooseMemorySearchDepths(
                    context.current_timestamp,
                    current_user_request,
                    task_conversation,
                    context.session_memories,
                    selected_task,
                    memory_search_hints,
                    root.memory.SearchDomains(),
                    context.search_depth_memories,
                    context.machine_state,
                );
            let search_depth_ms = search_depth_started_at.elapsed().to_milliseconds();
            root.memory
                .AddCandidateMemory(
                    candidate_memories,
                    root.memory.CandidateMemoryLayer.SEARCH_DEPTH,
                    search_depths.candidate_memory,
                );
            let understanding = VoicePromptUnderstanding {
                task_choice: task_choice,
                selected_task: selected_task,
                memory_search_hints: memory_search_hints,
                search_depths: search_depths,
                timings: VoicePromptUnderstandingTimings {
                    task_choice_ms: task_choice_ms,
                    memory_search_ms: memory_search_ms,
                    search_depth_ms: search_depth_ms,
                },
            };
            //# Retrieve memories
            let retrieved = retrieve_memories(context.cycle_id, understanding);
            //# Select memory
            let memory_relevance_started_at = baml.time.Instant.now();
            let relevance_decision = root
                .memory
                .SelectRelevantMemories(
                    current_user_request,
                    task_conversation,
                    context.session_memories,
                    selected_task,
                    root.memory
                        .Candidates(retrieved, context.current_session_id, context.user_preferences),
                    context.relevance_memories,
                    context.machine_state,
                );
            let memory_relevance_ms = memory_relevance_started_at.elapsed().to_milliseconds();
            root.memory
                .AddCandidateMemory(
                    candidate_memories,
                    root.memory.CandidateMemoryLayer.RELEVANCE,
                    relevance_decision.candidate_memory,
                );
            let selected_memories = root.memory.SelectedGraph(retrieved, relevance_decision);
            let selected_memory_contexts = root
                .task
                .PromptContexts(
                    selected_memories,
                    relevance_decision.kept_memory_ids,
                    context.current_session_id,
                    context.user_preferences,
                );
            //# Compose handoff
            let task_prompt_started_at = baml.time.Instant.now();
            let composition = root
                .task
                .ComposeTaskInput(
                    current_user_request,
                    task_conversation,
                    context.session_memories,
                    selected_task,
                    selected_memory_contexts,
                    context.task_prompt_memories,
                    context.machine_state,
                );
            let task_prompt_ms = task_prompt_started_at.elapsed().to_milliseconds();
            root.memory
                .AddCandidateMemory(
                    candidate_memories,
                    root.memory.CandidateMemoryLayer.TASK_PROMPT,
                    composition.candidate_memory,
                );
            let continuation = VoicePromptContinuation {
                relevance_decision: relevance_decision,
                selected_memories: selected_memories,
                selected_memory_contexts: selected_memory_contexts,
                task_prompt: root.task.PromptDecision(selected_task.prompt, composition),
                timings: VoicePromptContinuationTimings {
                    memory_relevance_ms: memory_relevance_ms,
                    task_prompt_ms: task_prompt_ms,
                },
            };

            let retry_context = root.task.TaskRetryContext { previous_replies: [], refusal_replies: [] };
            let task_prompt = continuation.task_prompt.full_task_prompt;
            //# Task attempts
            while (true) {
                //# Execute task
                let execution = execute_task(context.cycle_id, task_choice, task_prompt, continuation);
                let _ = dispatch_task_outputs(execution.attempt_id);
                let output_summary = summarize_task_actions(execution.attempt_id, task_choice)
                    ?? "No task output was produced.";
                let task_execution = execution.task_execution ?? root.task.TaskExecutionResult { returns: [] };
                //# Check completion
                let completion_started_at = baml.time.Instant.now();
                let task_completion_conversation = TaskConversation(load_request_conversation(), task_conversation_scope);
                let completion = root
                    .task
                    .CheckTaskCompletion(
                        selected_task.output,
                        output_summary,
                        current_user_request = current_user_request,
                        current_conversation = task_completion_conversation,
                    );
                let completion_ms = completion_started_at.elapsed().to_milliseconds();
                task_completion_ms += completion_ms;
                completion_reviews
                    .push(
                        VoiceTaskCompletionReview {
                            attempt_id: execution.attempt_id,
                            completion_string: selected_task.output,
                            output_summary: output_summary,
                            completion: completion,
                            elapsed_ms: completion_ms,
                        },
                    );
                let task_complete = completion == root.task.CompletionResult.PASS;
                if (task_complete) {
                    //# Complete task
                    let successful_task = SuccessfulVoiceTaskResult {
                        task_name: selected_task.name,
                        completion_requirement: selected_task.output,
                        output_summary: output_summary,
                    };
                    successful_tasks.push(successful_task);
                    let completed = CompletedVoiceTaskCycle {
                        cycle_id: context.cycle_id,
                        understanding: understanding,
                        retrieved_memories: retrieved,
                        continuation: continuation,
                        attempt_id: execution.attempt_id,
                        task_completion: completion,
                    };
                    completed_tasks.push(completed);
                    cycle_finished = true;
                    cycle_result
                        = CompletedVoiceTaskResult(completed, task_completion_ms, completion_reviews, failure_reviews);
                    break;
                } else {
                    //# Retry or reselect
                    let failure_started_at = baml.time.Instant.now();
                    let earlier_refusal_reply_text = root.task.internal.EarlierRefusalReplies(retry_context.refusal_replies);
                    let resolution = root
                        .task
                        .ResolveTaskFailure(
                            continuation.task_prompt.full_task_prompt,
                            selected_task.output,
                            output_summary,
                            task_execution,
                            retry_context,
                        );
                    let failure_ms = failure_started_at.elapsed().to_milliseconds();
                    task_completion_ms += failure_ms;
                    failure_reviews
                        .push(
                            VoiceTaskFailureReview {
                                attempt_id: execution.attempt_id,
                                task_prompt: continuation.task_prompt.full_task_prompt,
                                completion_string: selected_task.output,
                                output_summary: output_summary,
                                earlier_refusal_reply_text: earlier_refusal_reply_text,
                                decision: root.task.TaskFailureDecision {
                                    validation_reply: resolution.validation_reply,
                                    can_refine: resolution.can_refine,
                                },
                                elapsed_ms: failure_ms,
                            },
                        );
                    let _ = record_validation_reply(execution.attempt_id, resolution.validation_reply);
                    if (resolution.can_refine) {
                        //# Retry task
                        retry_context = resolution.retry_context;
                        task_prompt = resolution.retry_prompt;
                    } else {
                        //# Select another task
                        break;
                    }
                }
            }
        }
        let should_check = cycle_finished && consecutive_no_action_count < 3;
        let request_completion: root.task.CompletionResult? = null;
        //# Check request completion
        if (should_check) {
            let completion_conversation = TaskConversation(load_request_conversation(), load_task_conversation_scope());
            request_completion
                = CheckRequestCompletion(current_user_request, completion_conversation, successful_tasks);
        } else {
            //# Skip completion model
            null
        }
        let request_complete = cycle_finished && RequestIsComplete(consecutive_no_action_count, request_completion);
        if (request_complete) {
            //# Complete request
            voice_request_complete = true;
            request_result = cycle_result;
        } else {
            //# Choose another task
            continue;
        }
    }
    //# Review candidate memories
    let review_context = MemoryReviewContext(completion_context);
    let write_batch = ReviewMemories(candidate_memories, review_context);
    let memories_selected = root.memory.internal.HasSelectedCandidates(write_batch);
    if (memories_selected) {
        //# Save selected memories
        let _ = write_candidate_memories(write_batch);
    } else {
        //# Finish without saving
        null
    }
    //# Return result
    FinishedVoiceRequestResult(request_result)
}

function VoiceRequestResultAfterNoAction(
    completed_tasks: CompletedVoiceTaskCycle[],
    no_action: VoiceTaskNoActionResult,
    task_completion_ms: bigint,
    completion_reviews: VoiceTaskCompletionReview[],
    failure_reviews: VoiceTaskFailureReview[],
) -> VoiceTaskRunResult {
    if (completed_tasks.length() > 0) {
        CompletedVoiceTaskResult(
            completed_tasks[completed_tasks.length() - 1],
            task_completion_ms,
            completion_reviews,
            failure_reviews,
        )
    } else {
        no_action
    }
}

function FinishedVoiceRequestResult(state: VoiceRequestResultState) -> VoiceTaskRunResult {
    match (state) {
        let result: VoiceTaskFlowResult => result,
        let result: VoiceTaskNoActionResult => result,
        PendingVoiceRequestResult {} => baml.sys.panic("voice request completed without a result"),
    }
}

function CompletedVoiceTaskResult(
    completed: CompletedVoiceTaskCycle,
    task_completion_ms: bigint,
    completion_reviews: VoiceTaskCompletionReview[],
    failure_reviews: VoiceTaskFailureReview[],
) -> VoiceTaskFlowResult {
    VoiceTaskFlowResult {
        cycle_id: completed.cycle_id,
        understanding: completed.understanding,
        retrieved_memories: completed.retrieved_memories,
        continuation: completed.continuation,
        attempt_id: completed.attempt_id,
        task_completion: completed.task_completion,
        task_completion_ms: task_completion_ms,
        completion_reviews: completion_reviews,
        failure_reviews: failure_reviews,
    }
}

//# Filter active replies

function TaskConversation(
    conversation: root.turn_context.ConversationHistory?,
    scope: VoiceTaskConversationScope,
) -> root.turn_context.ConversationHistory? {
    if let current: root.turn_context.ConversationHistory = conversation {
        root.turn_context.ConversationHistory {
            id: current.id,
            name: current.name,
            created_at: current.created_at,
            updated_at: current.updated_at,
            read_at: current.read_at,
            messages: current
                .messages
                .filter(
                    (message) -> {
                        message.role != "human"
                            || !scope.active_human_reply_created_at.includes(message.created_at)
                            || message.created_at == scope.current_human_reply_created_at
                    },
                ),
        }
    } else {
        null
    }
}
