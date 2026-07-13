test "task prompt context preserves selected memory ancestry" {
    let graph = root.memory.RetrievedMemoryGraph {
        task_catalog: [],
        current_session_memories: [],
        past_sessions: [
            root.memory.RetrievedSessionGraph {
                session: root.memory.RetrievedSessionNode {
                    id: "session",
                    name: "Past session",
                    tags: [],
                    created_at: "2026-02-01T00:00:00Z",
                    updated_at: "2026-02-01T00:00:00Z",
                    read_at: "NONE",
                },
                matched: false,
                session_memories: [],
                conversations: [
                    root.memory.RetrievedConversationGraph {
                        conversation: root.memory.RetrievedConversationNode {
                            id: "conversation",
                            name: "Joke conversation",
                            tags: [],
                            created_at: "2026-02-01T00:00:00Z",
                            updated_at: "2026-02-01T00:00:00Z",
                            read_at: "NONE",
                        },
                        matched: false,
                        matched_message_ids: ["human-message"],
                        messages: [
                            root.memory.RetrievedConversationMessageNode {
                                id: "human-message",
                                role: "human",
                                content: "Tell me a joke.",
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
    let contexts = PromptContexts(graph, ["human-message"], null, []);
    assert
        .equal(
            contexts
                .map(
                    (context) -> {
                        context.title
                    },
                ),
            ["Past session: Past session", "Past conversation: Joke conversation", "human message"],
        )
}
