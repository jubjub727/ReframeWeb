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

test "task retry context keeps previous replies before stacked refusals" {
    let prompt = PromptWithRetryContext(
        "Task:\nReply.\n\nInput:\nHelp me.",
        [
            root.task.TaskAttemptReply { role: "agent_reply", content: "I tried the first answer." },
            root.task.TaskAttemptReply {
                role: "agent_thought",
                content: "The requested detail is still missing.",
            },
        ],
        ["The answer did not resolve the request.", "Use the supplied detail."],
    );
    assert.contains(prompt, "Previous Replies:\nagent_reply: I tried the first answer.");
    assert.contains(prompt, "agent_thought: The requested detail is still missing.");
    assert
        .contains(
            prompt,
            "Refusal Reply:\n- The answer did not resolve the request.\n- Use the supplied detail.",
        );
    let parts = prompt.split("Refusal Reply:");
    assert.equal(parts.length(), 2)
}

test "task retry context leaves a first attempt unchanged" {
    assert.equal(PromptWithRetryContext("Task prompt", [], []), "Task prompt")
}
