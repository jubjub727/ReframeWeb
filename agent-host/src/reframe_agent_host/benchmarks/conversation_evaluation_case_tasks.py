from __future__ import annotations

from reframe_agent_host.benchmarks.conversation_evaluation_case_types import (
    BenchmarkSelectedTask,
)


def visual_panel_task() -> BenchmarkSelectedTask:
    return BenchmarkSelectedTask(
        id="benchmark_task:visual_panel",
        name="Prepare visual panel",
        description="Prepare a visual panel for the user's browsing task.",
        input="The user's request and conversation context.",
        output="A visual panel plan and context needed to render it.",
        prompt="Prepare the visual panel requested by the user.",
        provider_id="benchmark_provider:core",
        **_timestamps("2026-07-02T09:00:00Z"),
    )


def needs_information_task() -> BenchmarkSelectedTask:
    return BenchmarkSelectedTask(
        id="benchmark_task:needs_information",
        name="Request more information from the user",
        description="Use when the request needs input before it can be handled.",
        input="The user's request and conversation context.",
        output="A concise question for the missing information.",
        prompt="Ask only for the information needed to continue.",
        provider_id="benchmark_provider:core",
        **_timestamps("2026-07-02T09:05:00Z"),
    )


def cannot_handle_task() -> BenchmarkSelectedTask:
    return BenchmarkSelectedTask(
        id="benchmark_task:cannot_handle",
        name="Explain request cannot be handled",
        description="Use when requested behavior is unsupported or unsafe.",
        input="The user's request and conversation context.",
        output="A clear explanation of the limitation.",
        prompt="Explain the limitation without pretending the request can be done.",
        provider_id="benchmark_provider:core",
        **_timestamps("2026-07-02T09:10:00Z"),
    )


def model_selection_task() -> BenchmarkSelectedTask:
    return BenchmarkSelectedTask(
        id="benchmark_task:model_selection",
        name="Choose model surface",
        description="Choose a model surface for an agentic flow step.",
        input="The user's request and conversation context.",
        output="The selected model surface.",
        prompt="Choose the model surface requested by the user.",
        provider_id="benchmark_provider:core",
        **_timestamps("2026-07-02T09:15:00Z"),
    )


def _timestamps(created_at: str) -> dict[str, str]:
    return {
        "created_at": created_at,
        "updated_at": created_at,
        "read_at": "NONE",
    }
