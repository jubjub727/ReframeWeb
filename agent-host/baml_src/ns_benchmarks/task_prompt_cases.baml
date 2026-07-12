function TaskPromptCases() -> TaskPromptBenchmarkCase[] {
    [
        TaskPromptBenchmarkCase {
            id: "stripe_followup_cleanup",
            current_user_request: "Do the same cleanup for the second Stripe CSV.",
            expected_task_name: "Request more information from the user",
            conversation_name: "Stripe CSV cleanup",
            messages: [
                TaskPromptCaseMessage {
                    role: "human",
                    content: "I downloaded January and February CSV exports from Stripe. January has duplicate rows after yesterday's export hiccup.",
                },
                TaskPromptCaseMessage {
                    role: "agent_thought",
                    content: "The user named two files conceptually but has not provided local paths.",
                },
                TaskPromptCaseMessage {
                    role: "agent",
                    content: "I can clean January first once you give me the file path, then apply the same duplicate-row cleanup to February.",
                },
            ],
            session_memories: [
                TaskPromptCaseMemory {
                    title: "Stripe export pair",
                    description: "The active cleanup conversation involves January and February Stripe CSV exports. January was described as having duplicate rows after an export hiccup.",
                    tags: ["stripe", "csv", "spreadsheet"],
                },
            ],
        },
        TaskPromptBenchmarkCase {
            id: "unsupported_visual_panel",
            current_user_request: "Open Hacker News in a compact visual panel even though the visual panel runner is not available yet.",
            expected_task_name: "Explain request cannot be handled",
            conversation_name: "Unsupported visual panel request",
            messages: [
                TaskPromptCaseMessage {
                    role: "human",
                    content: "When visual panels are ready, I like Hacker News as tight rows with scores and comment counts visible.",
                },
            ],
            session_memories: [
                TaskPromptCaseMemory {
                    title: "Hacker News compact preference",
                    description: "The user likes Hacker News as dense story rows: title first, score and comment count visible.",
                    tags: ["hacker-news", "visual-panel", "preference"],
                },
            ],
        },
    ]
}
