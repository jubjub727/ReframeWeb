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


def scroll_behavior_preference() -> ConversationEvaluationBenchmarkCase:
    return ConversationEvaluationBenchmarkCase(
        id="scroll_behavior_preference",
        current_user_request="When you open Reddit, scroll slower than last time.",
        selected_task=visual_panel_task(),
        session_conversations=(
            conversation(
                "scroll_behavior",
                "Browsing motion preference",
                (
                    human(
                        "The last Reddit thread felt jumpy because the panel "
                        "kept moving while I was still reading replies.",
                        "2026-07-02T14:10:00Z",
                    ),
                    thought(
                        "The user is reacting to Reddit thread motion: slower "
                        "scrolling and more time to read replies.",
                        "2026-07-02T14:10:03Z",
                    ),
                    agent(
                        "Understood. I will give Reddit threads more breathing "
                        "room when moving through replies.",
                        "2026-07-02T14:10:06Z",
                    ),
                    human(
                        "When you open Reddit, scroll slower than last time.",
                        "2026-07-02T14:30:00Z",
                    ),
                    thought(
                        "Task choice selected visual panel setup; the current "
                        "request points back to Reddit thread movement.",
                        "2026-07-02T14:30:02Z",
                    ),
                ),
            ),
        ),
        session_memories=(
            memory(
                "Reddit thread movement",
                "The user found Reddit discussion threads hard to read when "
                "the panel moved again before they finished reading replies.",
                ("preference", "visual-panel", "scrolling", "reddit"),
                "2026-07-02T14:10:08Z",
            ),
        ),
        conversation_evaluation_memories=(),
        review_focus="Review whether hints keep Reddit and scrolling as concrete references.",
    )
