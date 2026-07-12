function TaskChoiceMemories() -> BenchmarkMemory[] {
    [
        Memory(
            "Visual browsing task routing",
            "Requests to open, browse, scroll, or adjust a website view should usually select the visual panel preparation task.",
            ["task-choice", "visual-panel"],
            "2026-07-01T08:00:00Z",
        ),
        Memory(
            "Missing local file paths",
            "Spreadsheet cleanup requests need more information when the user has not provided concrete local file paths.",
            ["task-choice", "spreadsheet", "needs-information"],
            "2026-07-01T08:05:00Z",
        ),
    ]
}

function SearchDepthMemories() -> BenchmarkMemory[] {
    [
        Memory(
            "Followup depth",
            "Requests that reference earlier wording such as last time, this time, earlier this week, or the second one usually benefit from older conversation context.",
            ["search-depth", "followup"],
            "2026-07-01T07:30:00Z",
        ),
        Memory(
            "Stable task catalog",
            "Task catalog records change slowly during normal browsing and cleanup requests.",
            ["search-depth", "task-catalog"],
            "2026-07-01T07:35:00Z",
        ),
    ]
}

function HackerNewsCompactPanel() -> ControlFlowBenchmarkCase {
    let visual_task = VisualPanelTask();
    ControlFlowBenchmarkCase {
        id: "hacker_news_compact_panel",
        current_timestamp: "2026-07-03T15:00:00Z",
        current_user_request: "Open Hacker News, but keep it compact like last time.",
        expected_task_id: visual_task.id,
        available_tasks: AvailableTasks(),
        session: Session(
            "hacker_news_panel",
            "Hacker News visual panel session",
            [
                Conversation(
                    "hn_current_session",
                    "Hacker News panel preference",
                    [
                        Message(
                            "human",
                            "Hacker News worked best as tight rows of titles, scores, and comment counts. The preview cards made it feel too airy.",
                            "2026-07-02T10:00:00Z",
                        ),
                        Message(
                            "agent_thought",
                            "The user prefers a compact Hacker News layout with title-first rows and visible metadata.",
                            "2026-07-02T10:00:03Z",
                        ),
                        Message(
                            "agent",
                            "Got it. Hacker News should stay compact, with no expanded preview cards.",
                            "2026-07-02T10:00:06Z",
                        ),
                    ],
                ),
            ],
            [
                Memory(
                    "Hacker News row density",
                    "The user likes Hacker News as dense story rows: title first, score and comment count visible, and preview cards avoided.",
                    ["hacker-news", "visual-panel", "preference"],
                    "2026-07-02T10:00:08Z",
                ),
            ],
        ),
        task_choice_memories: TaskChoiceMemories(),
        user_preferences: [],
        conversation_evaluation_memories: [
            Memory(
                "Site display preference wording",
                "Requests using phrases like 'like last time' often need site-specific display preferences from prior browsing turns.",
                ["visual-panel", "preference", "followup"],
                "2026-07-01T09:00:00Z",
            ),
        ],
        search_depth_memories: SearchDepthMemories(),
        task_prompt_memories: [],
    }
}

function RedditSlowScroll() -> ControlFlowBenchmarkCase {
    let visual_task = VisualPanelTask();
    ControlFlowBenchmarkCase {
        id: "reddit_slow_scroll",
        current_timestamp: "2026-07-03T15:00:00Z",
        current_user_request: "Open the Reddit thread from earlier this week and scroll slower this time.",
        expected_task_id: visual_task.id,
        available_tasks: AvailableTasks(),
        session: Session(
            "reddit_motion",
            "Reddit visual panel session",
            [
                Conversation(
                    "reddit_motion",
                    "Reddit reading motion",
                    [
                        Message(
                            "human",
                            "The Reddit thread kept moving while I was still reading nested replies.",
                            "2026-06-30T21:15:00Z",
                        ),
                        Message(
                            "agent_thought",
                            "The user is reacting to browsing motion, not the Reddit content itself.",
                            "2026-06-30T21:15:03Z",
                        ),
                        Message(
                            "agent",
                            "I will give Reddit threads more time between scrolls.",
                            "2026-06-30T21:15:06Z",
                        ),
                    ],
                ),
            ],
            [
                Memory(
                    "Reddit scrolling pace",
                    "The user found Reddit discussion threads hard to read when the panel moved again before they finished nested replies.",
                    ["reddit", "visual-panel", "scrolling", "preference"],
                    "2026-06-30T21:15:08Z",
                ),
            ],
        ),
        task_choice_memories: TaskChoiceMemories(),
        user_preferences: [],
        conversation_evaluation_memories: [
            Memory(
                "Browsing motion corrections",
                "When the user mentions scrolling speed, search terms should keep both the site and motion wording.",
                ["visual-panel", "scrolling"],
                "2026-07-01T08:30:00Z",
            ),
        ],
        search_depth_memories: SearchDepthMemories(),
        task_prompt_memories: [],
    }
}

function StripeFollowupCleanup() -> ControlFlowBenchmarkCase {
    let information_task = NeedsInformationTask();
    ControlFlowBenchmarkCase {
        id: "stripe_followup_cleanup",
        current_timestamp: "2026-07-03T15:00:00Z",
        current_user_request: "Do the same cleanup for the second Stripe CSV.",
        expected_task_id: information_task.id,
        available_tasks: AvailableTasks(),
        session: Session(
            "stripe_csv_cleanup",
            "Stripe CSV cleanup session",
            [
                Conversation(
                    "stripe_csv_cleanup",
                    "Stripe CSV cleanup",
                    [
                        Message(
                            "human",
                            "I downloaded January and February CSV exports from Stripe. January has duplicate rows after yesterday's export hiccup.",
                            "2026-07-03T09:05:00Z",
                        ),
                        Message(
                            "agent_thought",
                            "The user named two files conceptually but has not provided local paths.",
                            "2026-07-03T09:05:03Z",
                        ),
                        Message(
                            "agent",
                            "I can clean January first once you give me the file path, then apply the same duplicate-row cleanup to February.",
                            "2026-07-03T09:05:06Z",
                        ),
                    ],
                ),
            ],
            [
                Memory(
                    "Stripe export pair",
                    "The active cleanup conversation involves January and February Stripe CSV exports. January was described as having duplicate rows after an export hiccup.",
                    ["stripe", "csv", "spreadsheet"],
                    "2026-07-03T09:05:08Z",
                ),
            ],
        ),
        task_choice_memories: TaskChoiceMemories(),
        user_preferences: [],
        conversation_evaluation_memories: [
            Memory(
                "Ambiguous second item",
                "Followups such as 'the second one' need the current and recent conversation objects preserved without guessing file paths.",
                ["followup", "spreadsheet"],
                "2026-07-02T17:00:00Z",
            ),
        ],
        search_depth_memories: SearchDepthMemories(),
        task_prompt_memories: [],
    }
}

function ControlFlowCases() -> ControlFlowBenchmarkCase[] {
    [HackerNewsCompactPanel(), RedditSlowScroll(), StripeFollowupCleanup()]
}
