from __future__ import annotations

from reframe_agent_host.benchmarks.control_flow_case_common import (
    CURRENT_TIMESTAMP,
    available_tasks,
    search_depth_memories,
    session,
    task_choice_memories,
)
from reframe_agent_host.benchmarks.control_flow_case_types import (
    ControlFlowBenchmarkCase,
)
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


def hacker_news_compact_panel() -> ControlFlowBenchmarkCase:
    visual_task = visual_panel_task()
    return ControlFlowBenchmarkCase(
        id="hacker_news_compact_panel",
        current_timestamp=CURRENT_TIMESTAMP,
        current_user_request="Open Hacker News, but keep it compact like last time.",
        expected_task_id=visual_task.id,
        available_tasks=available_tasks(),
        session=session(
            "hacker_news_panel",
            "Hacker News visual panel session",
            conversations=(
                conversation(
                    "hn_current_session",
                    "Hacker News panel preference",
                    (
                        human(
                            "Hacker News worked best as tight rows of titles, "
                            "scores, and comment counts. The preview cards made "
                            "it feel too airy.",
                            "2026-07-02T10:00:00Z",
                        ),
                        thought(
                            "The user prefers a compact Hacker News layout with "
                            "title-first rows and visible metadata.",
                            "2026-07-02T10:00:03Z",
                        ),
                        agent(
                            "Got it. Hacker News should stay compact, with no "
                            "expanded preview cards.",
                            "2026-07-02T10:00:06Z",
                        ),
                    ),
                ),
            ),
            memories=(
                memory(
                    "Hacker News row density",
                    "The user likes Hacker News as dense story rows: title first, "
                    "score and comment count visible, and preview cards avoided.",
                    ("hacker-news", "visual-panel", "preference"),
                    "2026-07-02T10:00:08Z",
                ),
            ),
        ),
        task_choice_memories=task_choice_memories(),
        conversation_evaluation_memories=(
            memory(
                "Site display preference wording",
                "Requests using phrases like 'like last time' often need "
                "site-specific display preferences from prior browsing turns.",
                ("visual-panel", "preference", "followup"),
                "2026-07-01T09:00:00Z",
            ),
        ),
        search_depth_memories=search_depth_memories(),
    )


def reddit_slow_scroll() -> ControlFlowBenchmarkCase:
    visual_task = visual_panel_task()
    return ControlFlowBenchmarkCase(
        id="reddit_slow_scroll",
        current_timestamp=CURRENT_TIMESTAMP,
        current_user_request=(
            "Open the Reddit thread from earlier this week and scroll slower this time."
        ),
        expected_task_id=visual_task.id,
        available_tasks=available_tasks(),
        session=session(
            "reddit_motion",
            "Reddit visual panel session",
            conversations=(
                conversation(
                    "reddit_motion",
                    "Reddit reading motion",
                    (
                        human(
                            "The Reddit thread kept moving while I was still "
                            "reading nested replies.",
                            "2026-06-30T21:15:00Z",
                        ),
                        thought(
                            "The user is reacting to browsing motion, not the "
                            "Reddit content itself.",
                            "2026-06-30T21:15:03Z",
                        ),
                        agent(
                            "I will give Reddit threads more time between scrolls.",
                            "2026-06-30T21:15:06Z",
                        ),
                    ),
                ),
            ),
            memories=(
                memory(
                    "Reddit scrolling pace",
                    "The user found Reddit discussion threads hard to read when "
                    "the panel moved again before they finished nested replies.",
                    ("reddit", "visual-panel", "scrolling", "preference"),
                    "2026-06-30T21:15:08Z",
                ),
            ),
        ),
        task_choice_memories=task_choice_memories(),
        conversation_evaluation_memories=(
            memory(
                "Browsing motion corrections",
                "When the user mentions scrolling speed, search terms should "
                "keep both the site and motion wording.",
                ("visual-panel", "scrolling"),
                "2026-07-01T08:30:00Z",
            ),
        ),
        search_depth_memories=search_depth_memories(),
    )
