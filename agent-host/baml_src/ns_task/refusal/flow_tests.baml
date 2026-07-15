test "refinable failure builds the next task-local prompt" {
    let resolution = root
        .task
        .internal
        .BuildTaskFailureResolution(
            "Task:\nReply.\n\nInput:\nHelp me.",
            TaskExecutionResult {
                returns: [
                    TaskReturnItem { name: "agent_reply", payload: { "text": "First reply." } },
                    TaskReturnItem { name: "agent_thought", payload: { "text": "First thought." } },
                    TaskReturnItem { name: "session_memory", payload: { "text": "Ignore this." } },
                ],
            },
            TaskRetryContext {
                previous_replies: [TaskAttemptReply { role: "agent_reply", content: "Earlier reply." }],
                refusal_replies: ["First refusal."],
            },
            TaskFailureDecision { validation_reply: "Second refusal.", can_refine: true },
        );
    assert.equal(resolution.can_refine, true);
    assert.not_null(resolution.retry_context);
    assert.contains(resolution.retry_prompt, "Previous Replies:\nagent_reply: Earlier reply.");
    assert.contains(resolution.retry_prompt, "agent_reply: First reply.");
    assert.contains(resolution.retry_prompt, "agent_thought: First thought.");
    assert
        .contains(
            resolution.retry_prompt,
            "Refusal Reply:\n- First refusal.\n- Second refusal.",
        )
}

test "non-refinable failure returns a typed resolution" {
    let resolution = root
        .task
        .internal
        .BuildTaskFailureResolution(
            "Task prompt",
            TaskExecutionResult { returns: [] },
            TaskRetryContext {
                previous_replies: [TaskAttemptReply { role: "agent_reply", content: "Old reply." }],
                refusal_replies: ["Old refusal."],
            },
            TaskFailureDecision { validation_reply: "Choose another task.", can_refine: false },
    );
    assert.equal(resolution.can_refine, false);
    assert.contains(resolution.retry_prompt, "Choose another task.")
}
