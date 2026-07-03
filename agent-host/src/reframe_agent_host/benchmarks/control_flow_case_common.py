from __future__ import annotations

from reframe_agent_host.benchmarks.conversation_evaluation_case_builders import memory
from reframe_agent_host.benchmarks.conversation_evaluation_case_types import (
    BenchmarkConversation,
    BenchmarkMemory,
    BenchmarkSelectedTask,
)
from reframe_agent_host.benchmarks.control_flow_case_types import BenchmarkSession
from reframe_agent_host.benchmarks.conversation_evaluation_case_tasks import (
    cannot_handle_task,
    needs_information_task,
    visual_panel_task,
)


CURRENT_TIMESTAMP = "2026-07-03T15:00:00Z"


def available_tasks() -> tuple[BenchmarkSelectedTask, ...]:
    return (
        visual_panel_task(),
        needs_information_task(),
        cannot_handle_task(),
    )


def session(
    id_suffix: str,
    name: str,
    conversations: tuple[BenchmarkConversation, ...],
    memories: tuple[BenchmarkMemory, ...],
) -> BenchmarkSession:
    timestamps = [
        item.created_at
        for item in (*conversations, *memories)
        if item.created_at != "NONE"
    ]
    created_at = min(timestamps) if timestamps else CURRENT_TIMESTAMP
    updated_at = max(
        [
            item.updated_at
            for item in (*conversations, *memories)
            if item.updated_at != "NONE"
        ]
        or [created_at]
    )
    return BenchmarkSession(
        id=f"benchmark_session:{id_suffix}",
        name=name,
        created_at=created_at,
        updated_at=updated_at,
        read_at="NONE",
        conversations=conversations,
        memories=memories,
    )


def task_choice_memories() -> tuple[BenchmarkMemory, ...]:
    return (
        memory(
            "Visual browsing task routing",
            "Requests to open, browse, scroll, or adjust a website view should "
            "usually select the visual panel preparation task.",
            ("task-choice", "visual-panel"),
            "2026-07-01T08:00:00Z",
        ),
        memory(
            "Missing local file paths",
            "Spreadsheet cleanup requests need more information when the user "
            "has not provided concrete local file paths.",
            ("task-choice", "spreadsheet", "needs-information"),
            "2026-07-01T08:05:00Z",
        ),
    )


def search_depth_memories() -> tuple[BenchmarkMemory, ...]:
    return (
        memory(
            "Followup depth",
            "Requests that reference earlier wording such as last time, this "
            "time, earlier this week, or the second one usually benefit from "
            "older conversation context.",
            ("search-depth", "followup"),
            "2026-07-01T07:30:00Z",
        ),
        memory(
            "Stable task catalog",
            "Task catalog records change slowly during normal browsing and "
            "cleanup requests.",
            ("search-depth", "task-catalog"),
            "2026-07-01T07:35:00Z",
        ),
    )
