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
    prompt: `
        ${role("system")}

        Produce concise validation guidance for this unsuccessful task attempt
        and decide whether the same selected task can sensibly be refined.

        Treat the task output summary as the delivered outcome. A terse result,
        fragment, raw value, or answer-only reply is not a failure unless the
        selected task prompt explicitly requires different presentation. The
        completion requirement identifies the intended outcome; it does not add
        unstated wording, framing, tone, or conversational ceremony. Diagnose the
        most direct substantive mismatch between the selected task prompt and the
        delivered outcome.

        Recorded delivery structures are envelopes, not user-visible content. If
        an agent, agent_reply, or agent_message record returned a text payload,
        treat that payload alone as the delivered reply. Do not describe its item
        name, role, field names, status, object syntax, or the summary wording
        around it as added framing or as a presentation defect unless the evidence
        explicitly places that material inside the payload.

        validation_reply must state the supported reason the result failed at
        useful specificity, identify what requirement, content, or action needs
        correction, and give concrete guidance about what should be checked or
        changed. A bare rejection or generic instruction to try again is not
        useful validation guidance.

        Shape the guidance so a repeated attempt is less likely to fail at the
        same point. Direct it toward a more reliable task-appropriate approach
        to the identified weakness without prescribing one universal method.
        When useful, favor a nudge that makes the next attempt easier to audit at
        that weak point before it is finalized. Merely asking it to check again
        is insufficient; the nudge should change its approach at that point.

        Address only the concrete failure that justified rejection. Do not add
        optional improvements, stylistic preferences, or new requirements.

        Perform any analysis needed to support the guidance internally. Keep the
        correct or expected outcome and its derivation internal. The guidance may
        identify the violated requirement, but it must not resolve that
        requirement for the next attempt. Do not provide a replacement result,
        exact corrected content, intermediate work, a worked solution, or an
        example that satisfies the request. If useful specificity would expose
        copyable target content, describe the weakness at a more abstract level.

        can_refine indicates whether another attempt with the same selected task
        is a sensible next step. Use false when task selection would be more
        useful.

        ${role("user")}

        Selected task prompt:
        ${task_prompt}

        Failed task output summary:
        ${output_summary}

        Earlier refusal replies from this task session:
        ${earlier_refusal_reply_text}

        ${role("system")}

        Return guidance, not a solution. Before responding, remove every resolved
        target, replacement output, partial answer, solved sub-result, identifying
        check value, derivation, and copyable example. Keep only the supported
        failure reason and a task-relative nudge toward a more reliable approach.
        Name the kind of correction abstractly; do not introduce illustrative
        answer content after phrases such as "for example" or "e.g.".

        ${role("user")}

        Return the corrective failure decision.
        ${ctx.output_format}
    `
}
