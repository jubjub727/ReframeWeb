from __future__ import annotations

from reframe_agent_host.benchmarks.conversation_evaluation_case_builders import (
    agent,
    conversation,
    human,
    memory,
    thought,
)
from reframe_agent_host.benchmarks.conversation_evaluation_case_tasks import (
    visual_panel_task,
)
from reframe_agent_host.benchmarks.conversation_evaluation_case_types import (
    ConversationEvaluationBenchmarkCase,
)


def remembered_view_preference() -> ConversationEvaluationBenchmarkCase:
    return ConversationEvaluationBenchmarkCase(
        id="remembered_view_preference",
        current_user_request="Open Hacker News, but keep it compact like last time.",
        selected_task=visual_panel_task(),
        session_conversations=(
            conversation(
                "view_preferences",
                "Hacker News display preference",
                (
                    human(
                        "Last time Hacker News felt good when it was just tight "
                        "rows of titles, scores, and comment counts. The preview "
                        "card version was too airy.",
                        "2026-07-02T10:00:00Z",
                    ),
                    thought(
                        "The user is describing a Hacker News density preference: "
                        "title-first rows, visible scores, and low vertical padding.",
                        "2026-07-02T10:00:03Z",
                    ),
                    agent(
                        "Got it. For Hacker News, compact means tight story rows "
                        "and no expanded preview cards.",
                        "2026-07-02T10:00:06Z",
                    ),
                    human(
                        "Open Hacker News, but keep it compact like last time.",
                        "2026-07-02T10:08:00Z",
                    ),
                    thought(
                        "Task choice selected visual panel setup; the request "
                        "references the earlier Hacker News display preference.",
                        "2026-07-02T10:08:02Z",
                    ),
                ),
            ),
        ),
        session_memories=(
            memory(
                "Hacker News row density",
                "The user reacted positively to Hacker News as a dense story "
                "list: title first, score and comment count visible, and preview "
                "cards avoided because they make the page feel airy.",
                ("preference", "hacker-news", "visual-panel"),
                "2026-07-02T10:00:08Z",
            ),
        ),
        conversation_evaluation_memories=(),
        review_focus="Review whether hints find the HN compact-row preference without being spoon-fed.",
    )


def voice_preference_recall() -> ConversationEvaluationBenchmarkCase:
    return ConversationEvaluationBenchmarkCase(
        id="voice_preference_recall",
        current_user_request="Keep your response short and don't read every result out.",
        selected_task=visual_panel_task(),
        session_conversations=(
            conversation(
                "voice_pace",
                "Voice pacing preferences",
                (
                    human(
                        "When we are in voice mode, I want the gist spoken out "
                        "loud and the noisy list left in the panel. Yesterday "
                        "hearing every search result was too much.",
                        "2026-07-02T13:20:00Z",
                    ),
                    thought(
                        "The user is separating spoken output from visual-panel "
                        "detail: short TTS, richer visible list.",
                        "2026-07-02T13:20:03Z",
                    ),
                    agent(
                        "Got it. I will speak the gist and keep the item-by-item "
                        "detail in the panel.",
                        "2026-07-02T13:20:06Z",
                    ),
                    human(
                        "Keep your response short and don't read every result out.",
                        "2026-07-02T13:27:00Z",
                    ),
                    thought(
                        "Task choice selected visual panel setup; the request "
                        "is about spoken output length while using a panel.",
                        "2026-07-02T13:27:02Z",
                    ),
                ),
            ),
        ),
        session_memories=(
            memory(
                "Voice result handling",
                "The user likes the spoken response to give only the gist while "
                "the visual panel carries individual results. A previous "
                "item-by-item spoken result list felt overwhelming.",
                ("voice", "tts", "visual-panel", "preference"),
                "2026-07-02T13:20:08Z",
            ),
        ),
        conversation_evaluation_memories=(
            memory(
                "Spoken versus visible detail",
                "Past voice-mode corrections often separated what should be "
                "spoken aloud from what should remain visible in a panel.",
                ("voice", "tts", "visual-panel"),
                "2026-07-02T09:45:00Z",
            ),
        ),
        review_focus="Review whether hints distinguish spoken output from visual-panel detail.",
    )
