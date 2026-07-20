function NextConsecutiveNoActionCount(
    selected_task: root.task_catalog.SelectedTaskContext,
    current_count: int,
) -> int {
    if (selected_task.model_id == "magic:do-nothing") {
        current_count + 1
    } else {
        0
    }
}

function RequestIsComplete(
    consecutive_no_action_count: int,
    completion: root.task.CompletionResult?,
) -> bool {
    if (consecutive_no_action_count >= 3) {
        true
    } else if let result: root.task.CompletionResult = completion {
        result == root.task.CompletionResult.PASS
    } else {
        false
    }
}
