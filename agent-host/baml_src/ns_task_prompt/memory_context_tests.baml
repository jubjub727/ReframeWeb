test "task prompt context exposes task intent without implementation fields" {
    let graph = root.retrieved_memory.RetrievedMemoryGraph {
        task_catalog: [
            root.retrieved_memory.RetrievedTaskNode {
                id: "task",
                name: "Prepare visual panel",
                description: "Task description",
                input: "private input contract",
                output: "private output contract",
                prompt: "private execution prompt",
                provider_id: "private provider",
                tags: [],
                created_at: "2026-02-01T00:00:00Z",
                updated_at: "2026-02-01T00:00:00Z",
                read_at: "NONE",
            },
        ],
        current_session_memories: [],
        past_sessions: [],
    };
    let contexts = PromptContexts(graph, ["task"], null, []);
    assert.equal(contexts.length(), 1);
    assert.equal(contexts[0].title, "Prepare visual panel");
    assert.equal(contexts[0].description, "Task description")
}
