testset "voice request completion state" {
    test "PASS completes the wider request" {
        assert.is_true(RequestIsComplete(0, root.task.CompletionResult.PASS))
    }

    test "FAIL continues the wider request" {
        assert.is_true(!RequestIsComplete(0, root.task.CompletionResult.FAIL))
    }

    test "third consecutive no action completes without a model result" {
        assert.is_true(RequestIsComplete(3, null))
    }

    test "real task resets the no action count" {
        let count = NextConsecutiveNoActionCount(RequestStateTask("magic:do-nothing"), 0);
        count = NextConsecutiveNoActionCount(RequestStateTask("magic:do-nothing"), count);
        assert.equal(count, 2);
        assert.equal(NextConsecutiveNoActionCount(RequestStateTask("glm-5.1"), count), 0)
    }

    test "completion parser preserves the shared PASS or FAIL result" {
        assert.equal(CheckRequestCompletion$parse("PASS"), root.task.CompletionResult.PASS);
        assert.equal(CheckRequestCompletion$parse("FAIL"), root.task.CompletionResult.FAIL)
    }
}

function RequestStateTask(model_id: string) -> root.task_catalog.SelectedTaskContext {
    root.task_catalog.SelectedTaskContext {
        id: "task",
        name: "Task",
        description: "Task description",
        input: "Task input",
        output: "Task output",
        prompt: "Task prompt",
        provider_id: "provider",
        model_id: model_id,
        created_at: "2026-07-01T00:00:00Z",
        updated_at: "2026-07-01T00:00:00Z",
        read_at: "2026-07-01T00:00:00Z",
    }
}
