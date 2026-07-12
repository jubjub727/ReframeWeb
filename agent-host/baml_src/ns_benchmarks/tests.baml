test "benchmark cases stay typed and available" {
    let control_cases = ControlFlowCases();
    let routing_cases = TaskChoiceCases();
    let prompt_cases = TaskPromptCases();
    assert.equal(control_cases.length(), 3);
    assert.equal(routing_cases.length(), 10);
    assert.equal(prompt_cases.length(), 2);
    assert.equal(control_cases[0].expected_task_id, "benchmark_task:visual_panel")
}

test "benchmark context conversion preserves conversation content" {
    let conversation = ConversationContext(HackerNewsCompactPanel().session.conversations[0]);
    assert.equal(conversation.messages[0].role, "human");
    assert.contains(conversation.messages[0].content, "Hacker News worked best")
}

test "task prompt evaluation requires both sections" {
    assert.is_true(EvaluateTaskPrompt("Task:\nDo it\nInput:\nUse context").correct);
    assert.is_true(!EvaluateTaskPrompt("Task:\nDo it").correct)
}

test "latency summary calculates the median" {
    let summary = SummariseLatencies([4.0, 1.0, 3.0, 2.0]);
    assert.equal(summary.average, 2.5);
    assert.equal(summary.p50, 2.5)
}
