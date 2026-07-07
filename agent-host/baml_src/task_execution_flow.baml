function PerformTask(full_task_prompt: string) -> TaskExecutionResult {
    client: TaskExecutionModel
    prompt: #"
        {{ _.role("system") }}

        Complete the task according to the task prompt and any guidance included in
        it.

        Rules:
        - You must follow the output shape requested by the task prompt.
        - When the task prompt describes named response items, put each item name in
          name and its arguments in payload.
        - You must only return response items for which you have direct evidence of its name and structure.
        - Do not add extra commentary outside the structured result.
        - Return an empty returns array when the task prompt does not request any
          response item.

        {{ _.role("user") }}

        Task prompt:
        {{ full_task_prompt }}

        Return the task execution result.
        {{ ctx.output_format }}
    "#
}

