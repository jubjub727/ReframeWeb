function CheckTaskCompletion(
    completion_string: string,
    output_summary: string,
) -> CompletionResult {
    client: TaskCompletionModel
    prompt: #"
        {{ _.role("system") }}

        You are a task completion checker.

        Compare the completion requirement to the task output summary.

        {{ _.role("user") }}

        Completion requirement:
        {{ completion_string }}

        Task output summary:
        {{ output_summary }}

        Return PASS only if the task output summary shows that the completion requirement was satisfied.

        Return FAIL if the summary does not satisfy the completion requirement, only partially satisfies it, or contradicts it.

        Return exactly one token:
        PASS or FAIL

        {{ ctx.output_format }}
    "#
}
