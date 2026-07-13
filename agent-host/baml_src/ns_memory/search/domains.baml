//# Build search scope

function SearchDomains() -> root.memory.SearchDepthDomain[] {
    [
        root.memory.SearchDepthDomain {
            id: "task_catalog",
            description: "Task catalog records. Use this domain when task definitions may help interpret or run the selected task.",
            searches: "Task memory nodes only.",
            hydrates: "Matched Task nodes only.",
        },
        root.memory.SearchDepthDomain {
            id: "past_conversation_context",
            description: "Historic conversation context outside the current default session context. Use this domain when earlier sessions, conversations, messages, or session memories may clarify the request.",
            searches: "Session nodes, Conversation nodes, ConversationMessage nodes, and SessionMemory nodes attached to those past sessions.",
            hydrates: "The containing Session node, relevant Conversation nodes, matched ConversationMessage nodes, and relevant SessionMemory nodes from that session.",
        },
    ]
}
