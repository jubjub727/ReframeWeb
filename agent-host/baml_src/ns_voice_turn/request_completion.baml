//# Check the original request

function CheckRequestCompletion(
    current_user_request: string,
    current_conversation: root.turn_context.ConversationHistory?,
    successful_tasks: SuccessfulVoiceTaskResult[],
) -> root.task.CompletionResult {
    client: RequestCompletionModel
    prompt: `
        ${role("system")}

        You are checking whether the user's original request is covered by the
        confirmed successful tasks or whether distinct work is still needed.

        This is a request-coverage check, not a task-result validator. Each item
        under Confirmed task results has already passed its own completion and
        quality validation. Treat those confirmations as authoritative here. Do
        not re-check their correctness, truthfulness, wording, or execution quality.

        Use the original request and conversation only to determine whether the
        confirmed tasks cover what the user asked for. A request can be covered by
        completed work, a reply, a necessary question, or a limitation response.

        Return PASS when the confirmed tasks cover the original request and no
        separate requested outcome remains.

        Return FAIL only when part of the original request has no corresponding
        confirmed task result and another distinct task is still needed.

        ${role("user")}

        Original user request:
        ${current_user_request}

        Current conversation:
        ${if (current_conversation != null) {
            current_conversation
        } else {
            ""
        }}

        Confirmed task results:
        ${successful_tasks.map((task) -> {
            `- Task: ${task.task_name}
          Completion requirement: ${task.completion_requirement}
          Result: ${task.output_summary}`
        }).join("\n")}

        Return exactly one token:
        PASS or FAIL

        ${ctx.output_format}
    `
}
