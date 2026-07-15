// Layout-memory case

function RememberedViewPreference() -> ConversationEvaluationBenchmarkCase {
    ConversationEvaluationBenchmarkCase {
        id: "remembered_view_preference",
        current_user_request: "Open Hacker News, but keep it compact like last time.",
        selected_task: VisualPanelTask(),
        session_conversations: [
            Conversation(
                "view_preferences",
                "Hacker News display preference",
                [
                    Message(
                        "human",
                        "Last time Hacker News felt good when it was just tight rows of titles, scores, and comment counts. The preview card version was too airy.",
                        "2026-07-02T10:00:00Z",
                    ),
                    Message(
                        "agent_thought",
                        "The user is describing a Hacker News density preference: title-first rows, visible scores, and low vertical padding.",
                        "2026-07-02T10:00:03Z",
                    ),
                    Message(
                        "agent",
                        "Got it. For Hacker News, compact means tight story rows and no expanded preview cards.",
                        "2026-07-02T10:00:06Z",
                    ),
                    Message(
                        "human",
                        "Open Hacker News, but keep it compact like last time.",
                        "2026-07-02T10:08:00Z",
                    ),
                    Message(
                        "agent_thought",
                        "Task choice selected visual panel setup; the request references the earlier Hacker News display preference.",
                        "2026-07-02T10:08:02Z",
                    ),
                ],
            ),
        ],
        session_memories: [
            Memory(
                "Hacker News row density",
                "The user reacted positively to Hacker News as a dense story list: title first, score and comment count visible, and preview cards avoided because they make the page feel airy.",
                ["preference", "hacker-news", "visual-panel"],
                "2026-07-02T10:00:08Z",
            ),
        ],
        conversation_evaluation_memories: [],
        review_focus: "Review whether hints find the HN compact-row preference without being spoon-fed.",
    }
}

// Ambiguous request

function AmbiguousFollowup() -> ConversationEvaluationBenchmarkCase {
    ConversationEvaluationBenchmarkCase {
        id: "ambiguous_followup",
        current_user_request: "Do the same thing for the second one.",
        selected_task: NeedsInformationTask(),
        session_conversations: [
            Conversation(
                "ambiguous_followup",
                "Spreadsheet cleanup discussion",
                [
                    Message(
                        "human",
                        "I downloaded the January and February CSV exports from Stripe. January has duplicate rows after yesterday's export hiccup.",
                        "2026-07-02T11:15:00Z",
                    ),
                    Message(
                        "agent_thought",
                        "The user has named two Stripe CSV exports and one operation, but has not provided any local file paths.",
                        "2026-07-02T11:15:03Z",
                    ),
                    Message(
                        "agent",
                        "I can clean January first once you give me the file path, then apply the same duplicate-row cleanup to February.",
                        "2026-07-02T11:15:06Z",
                    ),
                    Message("human", "Do the same thing for the second one.", "2026-07-02T11:17:00Z"),
                    Message(
                        "agent_thought",
                        "Task choice selected request-more-information; the second item is February, but the file path is still missing.",
                        "2026-07-02T11:17:02Z",
                    ),
                ],
            ),
        ],
        session_memories: [
            Memory(
                "Stripe export pair",
                "The active cleanup conversation involves two Stripe CSV exports named January and February. January was described as having duplicate rows after an export hiccup.",
                ["stripe", "csv", "spreadsheet"],
                "2026-07-02T11:15:08Z",
            ),
        ],
        conversation_evaluation_memories: [],
        review_focus: "Review whether hints preserve the CSV/Stripe context without guessing a file path.",
    }
}

// Capability case

function CapabilityLimitWithSensitiveAction() -> ConversationEvaluationBenchmarkCase {
    ConversationEvaluationBenchmarkCase {
        id: "capability_limit_with_sensitive_action",
        current_user_request: "Transfer the 500 dollars to Alex from my bank.",
        selected_task: CannotHandleTask(),
        session_conversations: [
            Conversation(
                "bank_transfer",
                "Bank transfer request",
                [
                    Message(
                        "human",
                        "Can you look at my bank site if I tell you what to do?",
                        "2026-07-02T12:00:00Z",
                    ),
                    Message(
                        "agent_thought",
                        "The user is asking about a private banking website, which may involve credentials, balances, or account actions.",
                        "2026-07-02T12:00:03Z",
                    ),
                    Message(
                        "agent",
                        "I can explain general steps, but I cannot log into private banking accounts or move money for you.",
                        "2026-07-02T12:00:06Z",
                    ),
                    Message(
                        "human",
                        "Transfer the 500 dollars to Alex from my bank.",
                        "2026-07-02T12:04:00Z",
                    ),
                    Message(
                        "agent_thought",
                        "Task choice selected cannot-handle response; the current request is a direct bank transfer.",
                        "2026-07-02T12:04:02Z",
                    ),
                ],
            ),
        ],
        session_memories: [
            Memory(
                "Bank website boundary",
                "Earlier in this session, the user asked about bank website control. The assistant answered that it can explain general steps but cannot log into private banking accounts or move money.",
                ["banking", "finance", "transaction"],
                "2026-07-02T12:00:08Z",
            ),
        ],
        conversation_evaluation_memories: [
            Memory(
                "Private account action wording",
                "Past finance-related turns mixed ordinary browser wording with transaction verbs such as transfer, pay, send, and move.",
                ["banking", "finance", "browser"],
                "2026-07-02T09:40:00Z",
            ),
        ],
        review_focus: "Review whether hints focus on banking/finance/transfer context without policy answer-key tags.",
    }
}

// Voice-memory case

function VoicePreferenceRecall() -> ConversationEvaluationBenchmarkCase {
    ConversationEvaluationBenchmarkCase {
        id: "voice_preference_recall",
        current_user_request: "Keep your response short and don't read every result out.",
        selected_task: VisualPanelTask(),
        session_conversations: [
            Conversation(
                "voice_pace",
                "Voice pacing preferences",
                [
                    Message(
                        "human",
                        "When we are in voice mode, I want the gist spoken out loud and the noisy list left in the panel. Yesterday hearing every search result was too much.",
                        "2026-07-02T13:20:00Z",
                    ),
                    Message(
                        "agent_thought",
                        "The user is separating spoken output from visual-panel detail: short TTS, richer visible list.",
                        "2026-07-02T13:20:03Z",
                    ),
                    Message(
                        "agent",
                        "Got it. I will speak the gist and keep the item-by-item detail in the panel.",
                        "2026-07-02T13:20:06Z",
                    ),
                    Message(
                        "human",
                        "Keep your response short and don't read every result out.",
                        "2026-07-02T13:27:00Z",
                    ),
                    Message(
                        "agent_thought",
                        "Task choice selected visual panel setup; the request is about spoken output length while using a panel.",
                        "2026-07-02T13:27:02Z",
                    ),
                ],
            ),
        ],
        session_memories: [
            Memory(
                "Voice result handling",
                "The user likes the spoken response to give only the gist while the visual panel carries individual results. A previous item-by-item spoken result list felt overwhelming.",
                ["voice", "tts", "visual-panel", "preference"],
                "2026-07-02T13:20:08Z",
            ),
        ],
        conversation_evaluation_memories: [
            Memory(
                "Spoken versus visible detail",
                "Past voice-mode corrections often separated what should be spoken aloud from what should remain visible in a panel.",
                ["voice", "tts", "visual-panel"],
                "2026-07-02T09:45:00Z",
            ),
        ],
        review_focus: "Review whether hints distinguish spoken output from visual-panel detail.",
    }
}

// Scroll-memory case

function ScrollBehaviorPreference() -> ConversationEvaluationBenchmarkCase {
    ConversationEvaluationBenchmarkCase {
        id: "scroll_behavior_preference",
        current_user_request: "When you open Reddit, scroll slower than last time.",
        selected_task: VisualPanelTask(),
        session_conversations: [
            Conversation(
                "scroll_behavior",
                "Browsing motion preference",
                [
                    Message(
                        "human",
                        "The last Reddit thread felt jumpy because the panel kept moving while I was still reading replies.",
                        "2026-07-02T14:10:00Z",
                    ),
                    Message(
                        "agent_thought",
                        "The user is reacting to Reddit thread motion: slower scrolling and more time to read replies.",
                        "2026-07-02T14:10:03Z",
                    ),
                    Message(
                        "agent",
                        "Understood. I will give Reddit threads more breathing room when moving through replies.",
                        "2026-07-02T14:10:06Z",
                    ),
                    Message(
                        "human",
                        "When you open Reddit, scroll slower than last time.",
                        "2026-07-02T14:30:00Z",
                    ),
                    Message(
                        "agent_thought",
                        "Task choice selected visual panel setup; the current request points back to Reddit thread movement.",
                        "2026-07-02T14:30:02Z",
                    ),
                ],
            ),
        ],
        session_memories: [
            Memory(
                "Reddit thread movement",
                "The user found Reddit discussion threads hard to read when the panel moved again before they finished reading replies.",
                ["preference", "visual-panel", "scrolling", "reddit"],
                "2026-07-02T14:10:08Z",
            ),
        ],
        conversation_evaluation_memories: [],
        review_focus: "Review whether hints keep Reddit and scrolling as concrete references.",
    }
}

//# Build search cases

function ConversationEvaluationCases() -> ConversationEvaluationBenchmarkCase[] {
    [
        RememberedViewPreference(),
        AmbiguousFollowup(),
        CapabilityLimitWithSensitiveAction(),
        VoicePreferenceRecall(),
        ScrollBehaviorPreference(),
    ]
}
