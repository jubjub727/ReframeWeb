class TaskReturnItem {
    name: string,
    payload: map<string, string>?,
}

class TaskExecutionResult {
    returns: TaskReturnItem[],
}
