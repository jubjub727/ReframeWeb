//# Resolve failed task

function ResolveTaskFailure(
    base_task_prompt: string,
    completion_string: string,
    output_summary: string,
    failed_execution: TaskExecutionResult,
    retry_context: TaskRetryContext,
) -> TaskFailureResolution {
    //# Write refusal reply
    let decision = WriteValidationReply(
        base_task_prompt,
        completion_string,
        output_summary,
        root.task.internal.EarlierRefusalReplies(retry_context.refusal_replies),
    );
    root.task
        .internal
        .BuildTaskFailureResolution(base_task_prompt, failed_execution, retry_context, decision)
}

//# Generate refusal reply

function WriteValidationReply(
    task_prompt: string,
    completion_string: string,
    output_summary: string,
    earlier_refusal_reply_text: string,
) -> TaskFailureDecision {
    client: TaskCompletionModel
    prompt: #"
        {{ _.role("system") }}

        Produce compact corrective context for what should happen after this
        unsuccessful task attempt.

        Guidance:
        - validation_reply must briefly state why the result cannot be accepted
          and what outcome is still needed.
        - Write validation_reply as self-contained corrective context for the
          next task attempt or task selection.
        - Keep validation_reply strictly diagnostic. Identify the requirement,
          claim, or action whose validation failed and the kind of correction or
          independent verification the next attempt needs.
        - Do not provide or suggest a replacement answer or exact response
          content. The next task attempt owns solution generation and factual
          derivation from the original task prompt.
        - can_refine indicates whether another attempt with the same selected
          task is a sensible next step. Use false when task selection would be
          more useful.

        {{ _.role("user") }}

        Selected task prompt:
        {{ task_prompt }}

        Completion requirement:
        {{ completion_string }}

        Failed task output summary:
        {{ output_summary }}

        Earlier refusal replies from this task session:
        {{ earlier_refusal_reply_text }}

        Return the corrective failure decision.
        {{ ctx.output_format }}
    "#
}
