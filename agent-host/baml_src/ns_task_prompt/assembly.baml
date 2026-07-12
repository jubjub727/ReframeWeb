function PromptText(selected_task_prompt: string, task_input: string) -> string {
    `Task:\n${selected_task_prompt}\n\nInput:\n${task_input}`
}

function PromptDecision(
    selected_task_prompt: string,
    composition: root.task_prompt.TaskPromptComposition,
) -> root.task_prompt.TaskPromptDecision {
    root.task_prompt.TaskPromptDecision {
        full_task_prompt: PromptText(selected_task_prompt, composition.task_input),
        candidate_memory: composition.candidate_memory,
    }
}
