function PromptText(selected_task_prompt: string, task_input: string) -> string {
    `Task:\n${selected_task_prompt}\n\nInput:\n${task_input}`
}

function PromptDecision(
    selected_task_prompt: string,
    composition: root.task.TaskPromptComposition,
) -> root.task.TaskPromptDecision {
    root.task.TaskPromptDecision {
        full_task_prompt: PromptText(selected_task_prompt, composition.task_input),
        candidate_memory: composition.candidate_memory,
    }
}
