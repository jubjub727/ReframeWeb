test "search domains describe their storage scope" {
    let domains = SearchDomains();
    assert
        .equal(
            domains
                .map(
                    (domain) -> {
                        domain.id
                    },
                ),
            ["task_catalog", "past_conversation_context"],
        );
    assert.equal(domains[0].searches, "Task memory nodes only.");
    assert
        .equal(
            domains[1].hydrates,
            "The containing Session node, relevant Conversation nodes, matched ConversationMessage nodes, and relevant SessionMemory nodes from that session.",
        )
}
