function SelectedTask(
    available_tasks: AvailableTask[],
    selected_task_id: string,
) -> SelectedTaskContext {
    for (let task in available_tasks) {
        if (task.id == selected_task_id) {
            return SelectedTaskContext {
                id: task.id,
                name: task.name,
                description: task.description,
                input: task.input,
                output: task.output,
                prompt: task.prompt,
                provider_id: task.provider_id,
                created_at: task.created_at,
                updated_at: task.updated_at,
                read_at: task.read_at,
            };
        }
    }
    throw baml.errors.InvalidArgument {
        message: `selected task does not exist in available task context: ${selected_task_id}`,
    }
}
