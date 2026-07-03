from __future__ import annotations

from dataclasses import dataclass

from reframe_agent_host.benchmarks.conversation_evaluation_case_types import (
    BenchmarkConversation,
    BenchmarkMemory,
    BenchmarkSelectedTask,
)


@dataclass(frozen=True)
class BenchmarkSession:
    id: str
    name: str
    created_at: str
    updated_at: str
    read_at: str
    conversations: tuple[BenchmarkConversation, ...] = ()
    memories: tuple[BenchmarkMemory, ...] = ()


@dataclass(frozen=True)
class ControlFlowBenchmarkCase:
    id: str
    current_timestamp: str
    current_user_request: str
    expected_task_id: str
    available_tasks: tuple[BenchmarkSelectedTask, ...]
    session: BenchmarkSession
    task_choice_memories: tuple[BenchmarkMemory, ...] = ()
    conversation_evaluation_memories: tuple[BenchmarkMemory, ...] = ()
    search_depth_memories: tuple[BenchmarkMemory, ...] = ()
