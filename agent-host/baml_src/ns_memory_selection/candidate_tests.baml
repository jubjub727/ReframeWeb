test "candidates flatten the retrieved graph and label the current session" {
    let graph = root.retrieved_memory.RetrievedMemoryGraph {
        task_catalog: [
            root.retrieved_memory.RetrievedTaskNode {
                id: "task",
                name: "Prepare visual panel",
                description: "Task description",
                input: "Task input",
                output: "Task output",
                prompt: "Task prompt",
                provider_id: "provider",
                tags: [],
                created_at: "2026-02-01T00:00:00Z",
                updated_at: "2026-02-01T00:00:00Z",
                read_at: "NONE",
            },
        ],
        current_session_memories: [
            root.retrieved_memory.RetrievedSessionMemoryNode {
                id: "current-memory",
                title: "Compact view",
                description: "Keep the view compact.",
                tags: [],
                created_at: "2026-02-01T00:00:00Z",
                updated_at: "2026-02-01T00:00:00Z",
                read_at: "NONE",
            },
        ],
        past_sessions: [
            root.retrieved_memory.RetrievedSessionGraph {
                session: root.retrieved_memory.RetrievedSessionNode {
                    id: "current-session",
                    name: "Current session",
                    tags: [],
                    created_at: "2026-02-01T00:00:00Z",
                    updated_at: "2026-02-01T00:00:00Z",
                    read_at: "NONE",
                },
                matched: true,
                session_memories: [],
                conversations: [
                    root.retrieved_memory.RetrievedConversationGraph {
                        conversation: root.retrieved_memory.RetrievedConversationNode {
                            id: "conversation",
                            name: "Layout conversation",
                            tags: [],
                            created_at: "2026-02-01T00:00:00Z",
                            updated_at: "2026-02-01T00:00:00Z",
                            read_at: "NONE",
                        },
                        matched: false,
                        matched_message_ids: ["message"],
                        messages: [
                            root.retrieved_memory.RetrievedConversationMessageNode {
                                id: "message",
                                role: "human",
                                content: "Keep it compact.",
                                tags: [],
                                created_at: "2026-02-01T00:00:00Z",
                                updated_at: "2026-02-01T00:00:00Z",
                                read_at: "NONE",
                            },
                        ],
                    },
                ],
            },
        ],
    };
    let candidates = Candidates(
        graph,
        "current-session",
        [
            root.context.UserPreferenceMemoryContext {
                id: "preference",
                title: "Density",
                description: "Prefer compact interfaces.",
                tags: [],
                created_at: "2026-02-01T00:00:00Z",
                updated_at: "2026-02-01T00:00:00Z",
                read_at: "NONE",
            },
        ],
    );
    assert
        .equal(
            candidates
                .map(
                    (candidate) -> {
                        candidate.id
                    },
                ),
            ["task", "current-memory", "preference", "current-session", "conversation", "message"],
        );
    assert
        .equal(
            candidates
                .map(
                    (candidate) -> {
                        candidate.kind
                    },
                ),
            [
                "task",
                "current_session_memory",
                "user_preference",
                "current_session",
                "current_conversation",
                "current_conversation_message",
            ],
        )
}
