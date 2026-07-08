test "candidate contexts flatten retrieved memory graph" {
    let graph = RetrievedMemoryGraph {
        task_catalog: [
            RetrievedTaskNode {
                id: "memory_node:task1",
                name: "Prepare visual panel",
                description: "Task description",
                input: "Task input",
                output: "Task output",
                prompt: "Task prompt",
                provider_id: "memory_node:provider",
                tags: [],
                created_at: "2026-02-01T00:00:00Z",
                updated_at: "2026-02-01T00:00:00Z",
                read_at: "NONE",
            },
        ],
        current_session_memories: [
            RetrievedSessionMemoryNode {
                id: "memory_node:currentmemory",
                title: "Current compact preference",
                description: "Memory description",
                tags: [],
                created_at: "2026-02-01T00:00:00Z",
                updated_at: "2026-02-01T00:00:00Z",
                read_at: "NONE",
            },
        ],
        past_sessions: [
            RetrievedSessionGraph {
                session: RetrievedSessionNode {
                    id: "memory_node:session1",
                    name: "Old session",
                    tags: [],
                    created_at: "2026-02-01T00:00:00Z",
                    updated_at: "2026-02-01T00:00:00Z",
                    read_at: "NONE",
                },
                matched: false,
                session_memories: [],
                conversations: [
                    RetrievedConversationGraph {
                        conversation: RetrievedConversationNode {
                            id: "memory_node:conversation1",
                            name: "HN layout conversation",
                            tags: [],
                            created_at: "2026-02-01T00:00:00Z",
                            updated_at: "2026-02-01T00:00:00Z",
                            read_at: "NONE",
                        },
                        matched: false,
                        matched_message_ids: ["memory_node:message1"],
                        messages: [
                            RetrievedConversationMessageNode {
                                id: "memory_node:message1",
                                role: "human",
                                content: "Please keep Hacker News compact.",
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
    let candidates = MemoryCandidates(
        graph,
        "memory_node:current",
        [
            UserPreferenceMemoryContext {
                id: "memory_node:pref1",
                title: "Global density preference",
                description: "Prefer compact interfaces.",
                tags: ["compact"],
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
            [
                "memory_node:task1",
                "memory_node:currentmemory",
                "memory_node:pref1",
                "memory_node:session1",
                "memory_node:conversation1",
                "memory_node:message1",
            ],
        )
}

test "task prompt decision stitches selected task prompt" {
    let decision = FinishTaskPrompt(
        "Ask only for what matters.",
        TaskPromptComposition { task_input: "Ask for the CSV path.", candidate_memory: null },
    );
    assert
        .equal(
            decision.full_task_prompt,
            "Task:\nAsk only for what matters.\n\nInput:\nAsk for the CSV path.",
        )
}
