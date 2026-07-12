test "selection keeps chosen children with their parent wrappers" {
    let graph = root.retrieved_memory.RetrievedMemoryGraph {
        task_catalog: [],
        current_session_memories: [],
        past_sessions: [
            root.retrieved_memory.RetrievedSessionGraph {
                session: root.retrieved_memory.RetrievedSessionNode {
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
                    root.retrieved_memory.RetrievedConversationGraph {
                        conversation: root.retrieved_memory.RetrievedConversationNode {
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
                            root.retrieved_memory.RetrievedConversationMessageNode {
                                id: "human-message",
                                role: "human",
                                content: "Tell me a joke.",
                                tags: [],
                                created_at: "2026-02-01T00:00:00Z",
                                updated_at: "2026-02-01T00:00:00Z",
                                read_at: "NONE",
                            },
                            root.retrieved_memory.RetrievedConversationMessageNode {
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
    let decision = root.memory_selection.RelevantMemoryDecision {
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

    let contexts = root.task_prompt.PromptContexts(selected, decision.kept_memory_ids, null, []);
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
