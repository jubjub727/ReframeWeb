test "task prompt decision stitches the selected task prompt" {
    let decision = PromptDecision(
        "Ask only for what matters.",
        root.task.TaskPromptComposition {
            task_input: "Ask for the CSV path.",
            candidate_memory: null,
        },
    );
    assert
        .equal(
            decision.full_task_prompt,
            "Task:\nAsk only for what matters.\n\nInput:\nAsk for the CSV path.",
        )
}
