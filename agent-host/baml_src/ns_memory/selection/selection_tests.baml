test "selection keeps chosen children with their parent wrappers" {
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
                            root.memory.RetrievedConversationMessageNode {
                                id: "agent-message",
                                role: "agent",
                                content: "Unselected reply.",
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
    let decision = root.memory.RelevantMemoryDecision {
        kept_memory_ids: ["human-message"],
        candidate_memory: null,
    };
    let selected = SelectedGraph(graph, decision);
    assert
        .equal(
            selected
                .past_sessions
                .map(
                    (item) -> {
                        item.session.id
                    },
                ),
            ["session"],
        );
    assert
        .equal(
            selected
                .past_sessions[0]
                .conversations
                .map(
                    (item) -> {
                        item.conversation.id
                    },
                ),
            ["conversation"],
        );
    assert
        .equal(
            selected
                .past_sessions[0]
                .conversations[0]
                .messages
                .map(
                    (item) -> {
                        item.id
                    },
                ),
            ["human-message"],
        );
}
