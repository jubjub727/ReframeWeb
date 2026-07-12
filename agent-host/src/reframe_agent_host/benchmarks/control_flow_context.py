from __future__ import annotations

from baml_sdk import context as baml_context
from baml_sdk import memory_search as baml_memory_search
from baml_sdk import task_routing as baml_task_routing
from reframe_agent_host.benchmarks.conversation_evaluation_case_types import (
    BenchmarkMemory,
    BenchmarkSelectedTask,
)
from reframe_agent_host.benchmarks.conversation_evaluation_context import (
    conversation_context,
    memory_context,
    selected_task_context,
)
from reframe_agent_host.benchmarks.control_flow_case_types import (
    ControlFlowBenchmarkCase,
)


def available_task_context(
    tasks: tuple[BenchmarkSelectedTask, ...],
) -> list[baml_task_routing.AvailableTask]:
    return [
        baml_task_routing.AvailableTask(
            id=task.id,
            name=task.name,
            description=task.description,
            input=task.input,
            output=task.output,
            prompt=task.prompt,
            provider_id=task.provider_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
            read_at=task.read_at,
        )
        for task in tasks
    ]


def task_choice_memory_context(
    memories: tuple[BenchmarkMemory, ...],
) -> list[baml_task_routing.TaskChoiceMemoryContext]:
    return [
        baml_task_routing.TaskChoiceMemoryContext(
            title=memory.title,
            description=memory.description,
            tags=list(memory.tags),
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            read_at=memory.read_at,
        )
        for memory in memories
    ]


def user_preference_context(
    memories: tuple[BenchmarkMemory, ...],
) -> list[baml_context.UserPreferenceMemoryContext]:
    return [
        baml_context.UserPreferenceMemoryContext(
            id=f"memory_node:user_preference_{index}",
            title=memory.title,
            description=memory.description,
            tags=list(memory.tags),
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            read_at=memory.read_at,
        )
        for index, memory in enumerate(memories)
    ]


def search_depth_memory_context(
    memories: tuple[BenchmarkMemory, ...],
) -> list[baml_memory_search.SearchDepthMemoryContext]:
    return [
        baml_memory_search.SearchDepthMemoryContext(
            title=memory.title,
            description=memory.description,
            tags=list(memory.tags),
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            read_at=memory.read_at,
        )
        for memory in memories
    ]


def selected_task_from_case(
    case: ControlFlowBenchmarkCase,
    selected_task_id: str,
) -> baml_task_routing.SelectedTaskContext:
    for task in case.available_tasks:
        if task.id == selected_task_id:
            return selected_task_context(task)

    msg = f"selected task not available in case {case.id}: {selected_task_id}"
    raise ValueError(msg)


def case_conversation_context(
    case: ControlFlowBenchmarkCase,
) -> list[baml_context.ConversationHistory]:
    return conversation_context(case.session.conversations)


def case_session_memory_context(
    case: ControlFlowBenchmarkCase,
) -> list[baml_context.SessionMemoryContext]:
    return memory_context(case.session.memories)


__all__ = [
    "available_task_context",
    "case_conversation_context",
    "case_session_memory_context",
    "conversation_context",
    "memory_context",
    "search_depth_memory_context",
    "selected_task_from_case",
    "task_choice_memory_context",
    "user_preference_context",
]
