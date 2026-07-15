//# Build resolution

function BuildTaskFailureResolution(
    base_task_prompt: string,
    failed_execution: root.task.TaskExecutionResult,
    retry_context: root.task.TaskRetryContext,
    decision: root.task.TaskFailureDecision,
) -> root.task.TaskFailureResolution {
    let validation_reply = decision.validation_reply.trim();
    let next_context = root.task.TaskRetryContext {
        previous_replies: retry_context.previous_replies.concat(PreviousTaskReplies(failed_execution)),
        refusal_replies: retry_context.refusal_replies.concat([validation_reply]),
    };
    root.task.TaskFailureResolution {
        validation_reply: validation_reply,
        can_refine: decision.can_refine,
        retry_context: next_context,
        retry_prompt: root
            .task
            .PromptWithRetryContext(
                base_task_prompt,
                next_context.previous_replies,
                next_context.refusal_replies,
            ),
    }
}

//# Collect previous replies

function PreviousTaskReplies(
    execution: root.task.TaskExecutionResult,
) -> root.task.TaskAttemptReply[] {
    execution
        .returns
        .filter(
            (item) -> {
                item.name == "agent_reply" || item.name == "agent_thought"
            },
        )
        .filter(
            (item) -> {
                (item.payload?.get("text")?.trim() ?? "") != ""
            },
        )
        .map(
            (item) -> {
                root.task.TaskAttemptReply {
                    role: item.name,
                    content: item.payload?.get("text")?.trim() ?? "",
                }
            },
        )
}

//# Format refusals

function EarlierRefusalReplies(replies: string[]) -> string {
    replies
        .map(
            (reply) -> {
                `- ${reply}`
            },
        )
        .join("\n")
}
