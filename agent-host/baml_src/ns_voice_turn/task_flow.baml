//# Run complete voice turn

function RunVoiceTurn(
    current_user_request: string,
    load_context: () -> VoiceTaskFlowContext,
    retrieve_memories: (
        string,
        VoicePromptUnderstanding,
    ) -> root.memory.RetrievedMemoryGraph,
    execute_task: (
        string,
        root.task.TaskChoiceDecision,
        string,
        VoicePromptContinuation,
    ) -> VoiceTaskExecutionBoundaryResult,
    dispatch_task_outputs: (string) -> bool,
    summarize_task_actions: (string, root.task.TaskChoiceDecision) -> string?,
    record_validation_reply: (string, string) -> bool,
) -> VoiceTaskFlowResult {
    let task_completion_ms = 0n;
    //# Task selection
    while (true) {
        //# Load context
        let context = load_context();

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
        let selected_task = root
            .task_catalog
            .SelectedTask(context.available_tasks, task_choice.selected_task_id);

        //# Plan memory search
        let memory_search_started_at = baml.time.Instant.now();
        let memory_search_hints = root
            .memory
            .ChooseMemorySearch(
                current_user_request,
                context.current_conversation,
                context.session_memories,
                selected_task,
                context.conversation_evaluation_memories,
                context.machine_state,
            );
        let memory_search_ms = memory_search_started_at.elapsed().to_milliseconds();

        //# Set search depth
        let search_depth_started_at = baml.time.Instant.now();
        let search_depths = root
            .memory
            .ChooseMemorySearchDepths(
                context.current_timestamp,
                current_user_request,
                context.current_conversation,
                context.session_memories,
                selected_task,
                memory_search_hints,
                root.memory.SearchDomains(),
                context.search_depth_memories,
                context.machine_state,
            );
        let search_depth_ms = search_depth_started_at.elapsed().to_milliseconds();
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
                context.current_conversation,
                context.session_memories,
                selected_task,
                root
                    .memory
                    .Candidates(
                        retrieved,
                        context.current_session_id,
                        context.user_preferences,
                    ),
                context.relevance_memories,
                context.machine_state,
            );
        let memory_relevance_ms = memory_relevance_started_at.elapsed().to_milliseconds();
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
                context.current_conversation,
                context.session_memories,
                selected_task,
                selected_memory_contexts,
                context.task_prompt_memories,
                context.machine_state,
            );
        let task_prompt_ms = task_prompt_started_at.elapsed().to_milliseconds();
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

        let retry_context = root.task.TaskRetryContext {
            previous_replies: [],
            refusal_replies: [],
        };
        let task_prompt = continuation.task_prompt.full_task_prompt;
        //# Task attempts
        while (true) {
            //# Execute task
            let execution = execute_task(
                context.cycle_id,
                task_choice,
                task_prompt,
                continuation,
            );
            let _ = dispatch_task_outputs(execution.attempt_id);
            let output_summary = summarize_task_actions(
                execution.attempt_id,
                task_choice,
            ) ?? "No task output was produced.";
            let task_execution = execution.task_execution
                ?? root.task.TaskExecutionResult { returns: [] };

            //# Check completion
            let completion_started_at = baml.time.Instant.now();
            let completion = root
                .task
                .CheckTaskCompletion(selected_task.output, output_summary);
            task_completion_ms += completion_started_at.elapsed().to_milliseconds();
            match (completion) {
                root.task.CompletionResult.PASS => {
                    return VoiceTaskFlowResult {
                        cycle_id: context.cycle_id,
                        understanding: understanding,
                        retrieved_memories: retrieved,
                        continuation: continuation,
                        attempt_id: execution.attempt_id,
                        task_completion: completion,
                        task_completion_ms: task_completion_ms,
                    };
                }
                root.task.CompletionResult.FAIL => {
                    //# Retry or reselect
                    let failure_started_at = baml.time.Instant.now();
                    let resolution = root
                        .task
                        .ResolveTaskFailure(
                            continuation.task_prompt.full_task_prompt,
                            selected_task.output,
                            output_summary,
                            task_execution,
                            retry_context,
                        );
                    task_completion_ms += failure_started_at.elapsed().to_milliseconds();
                    let _ = record_validation_reply(
                        execution.attempt_id,
                        resolution.validation_reply,
                    );
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
    }
    baml.sys.panic("voice task flow ended without a completed task")
}
