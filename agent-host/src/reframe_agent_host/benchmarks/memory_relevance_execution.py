from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import re
import time
from typing import Any

from baml_core import Collector

from reframe_agent_host.agent_flow.memory_retrieval import (
    _search_hints,
    _timestamp_breadths,
)
from reframe_agent_host.agent_flow.machine_state import local_machine_state_context
from reframe_agent_host.agent_flow.relevance_candidates import candidate_contexts
import baml_sdk as baml
import baml_sdk as types
from reframe_agent_host.agent_flow.baml_clients import client_kwargs
from reframe_agent_host.benchmarks.control_flow_case_types import (
    ControlFlowBenchmarkCase,
)
from reframe_agent_host.benchmarks.control_flow_execution import (
    ControlFlowSnapshot,
    build_control_flow_snapshot,
    search_depths,
)
from reframe_agent_host.benchmarks.control_flow_context import (
    user_preference_context,
)
from reframe_agent_host.benchmarks.reasoning_efforts import (
    collector_stop_reason,
    collector_usage,
)
from reframe_memory import (
    Conversation,
    ConversationMessage,
    GraphMemoryRetriever,
    GraphRetrievalRequest,
    MemoryNode,
    MemoryTimestamps,
    RetrievedMemoryContext,
    Session,
    SessionMemory,
    Task,
)


@dataclass(frozen=True)
class MemoryRelevanceSnapshot:
    case: ControlFlowBenchmarkCase
    control_flow: ControlFlowSnapshot
    search_depths: Any | None
    retrieved_memories: RetrievedMemoryContext | None
    candidate_memories: list[types.RetrievedMemoryCandidate]
    expected_kept_memory_ids: tuple[str, ...]
    relevance_memories: list[types.RelevanceMemoryContext]
    latency_seconds: float
    stage_latency_seconds: dict[str, float]
    error: str | None = None

    @property
    def selected_task_id(self) -> str | None:
        return self.control_flow.selected_task_id

    @property
    def task_correct(self) -> bool:
        return self.control_flow.task_correct


async def build_memory_relevance_snapshot(
    case: ControlFlowBenchmarkCase,
    client=None,
) -> MemoryRelevanceSnapshot:
    total_started_at = time.perf_counter()
    control = await build_control_flow_snapshot(case, client=client)
    stage_latencies = dict(control.stage_latency_seconds)
    expected_ids = _expected_kept_ids(case)
    relevance_memories: list[types.RelevanceMemoryContext] = []
    depths = None
    retrieved = None
    candidates: list[types.RetrievedMemoryCandidate] = []

    if control.error is not None:
        return MemoryRelevanceSnapshot(
            case=case,
            control_flow=control,
            search_depths=None,
            retrieved_memories=None,
            candidate_memories=[],
            expected_kept_memory_ids=expected_ids,
            relevance_memories=relevance_memories,
            latency_seconds=time.perf_counter() - total_started_at,
            stage_latency_seconds=stage_latencies,
            error=control.error,
        )

    try:
        depths, depth_latency = await search_depths(client, control)
        stage_latencies["search_depth"] = depth_latency
        retrieved, retrieval_latency = await _retrieve_memory_context(control, depths)
        stage_latencies["memory_retrieval"] = retrieval_latency
        candidates = candidate_contexts(
            retrieved,
            current_session_id=_session_node_id(case),
            user_preferences=user_preference_context(case.user_preferences),
        )
    except Exception as exc:
        return MemoryRelevanceSnapshot(
            case=case,
            control_flow=control,
            search_depths=depths,
            retrieved_memories=retrieved,
            candidate_memories=candidates,
            expected_kept_memory_ids=expected_ids,
            relevance_memories=relevance_memories,
            latency_seconds=time.perf_counter() - total_started_at,
            stage_latency_seconds=stage_latencies,
            error=str(exc),
        )

    return MemoryRelevanceSnapshot(
        case=case,
        control_flow=control,
        search_depths=depths,
        retrieved_memories=retrieved,
        candidate_memories=candidates,
        expected_kept_memory_ids=expected_ids,
        relevance_memories=relevance_memories,
        latency_seconds=time.perf_counter() - total_started_at,
        stage_latency_seconds=stage_latencies,
    )


async def run_memory_relevance_case(
    client,
    provider,
    snapshot: MemoryRelevanceSnapshot,
    run_index: int,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    case = snapshot.case
    collector = Collector(
        name=(
            f"memory-relevance-{provider.id}-{reasoning_effort or 'default'}-"
            f"{case.id}-{run_index}"
        )
    )
    if snapshot.error is not None:
        return {
            "case_id": case.id,
            "run_index": run_index,
            "provider_id": provider.id,
            "reasoning_effort": reasoning_effort,
            "expected_kept_memory_ids": list(snapshot.expected_kept_memory_ids),
            "selected_task_id": snapshot.selected_task_id,
            "task_correct": snapshot.task_correct,
            "snapshot_error": True,
            "error": f"snapshot failed: {snapshot.error}",
            "latency_seconds": time.perf_counter() - started_at,
        }

    try:
        decision, relevance_latency = await relevant_memories(client, snapshot)
    except Exception as exc:
        return {
            "case_id": case.id,
            "run_index": run_index,
            "provider_id": provider.id,
            "reasoning_effort": reasoning_effort,
            "expected_kept_memory_ids": list(snapshot.expected_kept_memory_ids),
            "selected_task_id": snapshot.selected_task_id,
            "task_correct": snapshot.task_correct,
            "error": str(exc),
            "latency_seconds": time.perf_counter() - started_at,
            "usage": collector_usage(collector),
            "stop_reason": collector_stop_reason(collector),
        }

    kept_ids = list(decision.kept_memory_ids)
    expected_ids = list(snapshot.expected_kept_memory_ids)
    return {
        "case_id": case.id,
        "run_index": run_index,
        "provider_id": provider.id,
        "reasoning_effort": reasoning_effort,
        "expected_kept_memory_ids": expected_ids,
        "kept_memory_ids": kept_ids,
        "correct": set(kept_ids) == set(expected_ids),
        "selected_task_id": snapshot.selected_task_id,
        "task_correct": snapshot.task_correct,
        "decision": decision.model_dump(mode="json"),
        "latency_seconds": relevance_latency,
        "stage_latency_seconds": {"memory_relevance": relevance_latency},
        "usage": collector_usage(collector),
        "stop_reason": collector_stop_reason(collector),
    }


async def warmup_memory_relevance(client, snapshots, config) -> int:
    errors = 0
    usable = [snapshot for snapshot in snapshots if snapshot.error is None]
    if config.warmup_runs < 1 or not usable:
        return errors

    for _ in range(config.warmup_runs):
        try:
            await relevant_memories(client, usable[0])
        except Exception:
            errors += 1
        if config.delay_seconds > 0:
            await asyncio.sleep(config.delay_seconds)
    return errors


async def relevant_memories(
    client,
    snapshot: MemoryRelevanceSnapshot,
):
    started_at = time.perf_counter()
    result = await baml.SelectRelevantMemories_async(
        current_user_request=snapshot.case.current_user_request,
        current_conversation=_current_conversation(
            snapshot.control_flow.session_conversations
        ),
        session_memories=snapshot.control_flow.session_memories,
        selected_task=snapshot.control_flow.selected_task,
        candidate_memories=snapshot.candidate_memories,
        relevance_memories=snapshot.relevance_memories,
        machine_state=local_machine_state_context("Benchmark machine state"),
        **client_kwargs(client),
    )
    return result, time.perf_counter() - started_at


def _current_conversation(conversations):
    return conversations[0] if conversations else None


def snapshot_payload(snapshot: MemoryRelevanceSnapshot) -> dict[str, Any]:
    payload = {
        "case_id": snapshot.case.id,
        "current_user_request": snapshot.case.current_user_request,
        "expected_task_id": snapshot.case.expected_task_id,
        "selected_task_id": snapshot.selected_task_id,
        "task_correct": snapshot.task_correct,
        "expected_kept_memory_ids": list(snapshot.expected_kept_memory_ids),
        "latency_seconds": snapshot.latency_seconds,
        "stage_latency_seconds": dict(snapshot.stage_latency_seconds),
        "relevance_input_snapshot": {
            "current_conversation": _dump_model(
                _current_conversation(snapshot.control_flow.session_conversations)
            ),
            "session_memories": _dump_models(snapshot.control_flow.session_memories),
            "selected_task": _dump_model(snapshot.control_flow.selected_task),
            "search_hints": _dump_model(snapshot.control_flow.search_hints),
            "search_depths": _dump_model(snapshot.search_depths),
            "retrieved_memories": (
                snapshot.retrieved_memories.to_dict()
                if snapshot.retrieved_memories is not None
                else None
            ),
            "candidate_memories": _dump_models(snapshot.candidate_memories),
            "relevance_memories": _dump_models(snapshot.relevance_memories),
        },
    }
    if snapshot.error is not None:
        payload["error"] = snapshot.error
    return payload


async def _retrieve_memory_context(control: ControlFlowSnapshot, depths):
    started_at = time.perf_counter()
    case = control.case
    retriever = GraphMemoryRetriever(
        _CaseMemoryDatabase(case),
        current_session_id=_session_node_id(case),
    )
    result = await retriever.retrieve(
        GraphRetrievalRequest(
            hints=_search_hints(control.search_hints),
            depths=_timestamp_breadths(depths),
        )
    )
    return result, time.perf_counter() - started_at


class _CaseMemoryDatabase:
    def __init__(self, case: ControlFlowBenchmarkCase) -> None:
        self.tasks = _CaseTasks(case)
        self.sessions = _CaseSessions(case)
        self.conversations = _CaseConversations(case)


class _CaseTasks:
    def __init__(self, case: ControlFlowBenchmarkCase) -> None:
        self._tasks = [
            _node(
                _task_node_id(task.id),
                tags=(),
                content=Task(
                    name=task.name,
                    description=task.description,
                    input=task.input,
                    output=task.output,
                    prompt=task.prompt,
                    provider_id=task.provider_id,
                ),
                created_at=task.created_at,
                updated_at=task.updated_at,
                read_at=task.read_at,
            )
            for task in case.available_tasks
        ]

    async def search(self):
        return self._tasks


class _CaseSessions:
    def __init__(self, case: ControlFlowBenchmarkCase) -> None:
        self._case = case
        self._session = _node(
            _session_node_id(case),
            tags=(),
            content=Session(name=case.session.name),
            created_at=case.session.created_at,
            updated_at=case.session.updated_at,
            read_at=case.session.read_at,
        )
        self._conversations = [
            _node(
                _conversation_node_id(case, index),
                tags=(),
                content=Conversation(name=conversation.name),
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                read_at=conversation.read_at,
            )
            for index, conversation in enumerate(case.session.conversations)
        ]
        self._memories = [
            _node(
                _session_memory_node_id(case, index),
                tags=memory.tags,
                content=SessionMemory(
                    title=memory.title,
                    description=memory.description,
                ),
                created_at=memory.created_at,
                updated_at=memory.updated_at,
                read_at=memory.read_at,
            )
            for index, memory in enumerate(case.session.memories)
        ]

    async def search(self):
        return [self._session]

    async def conversations_for(self, session_id):
        if session_id != self._session.id:
            return []
        return self._conversations

    async def memories_for(self, session_id):
        if session_id != self._session.id:
            return []
        return self._memories


class _CaseConversations:
    def __init__(self, case: ControlFlowBenchmarkCase) -> None:
        self._messages = {
            _conversation_node_id(case, conversation_index): [
                _node(
                    _message_node_id(case, conversation_index, message_index),
                    tags=(),
                    content=ConversationMessage(
                        role=message.role,
                        content=message.content,
                    ),
                    created_at=message.created_at,
                    updated_at=message.updated_at,
                    read_at=message.read_at,
                )
                for message_index, message in enumerate(conversation.messages)
            ]
            for conversation_index, conversation in enumerate(
                case.session.conversations
            )
        }

    async def messages_for(self, conversation_id):
        return self._messages.get(conversation_id, [])


def _expected_kept_ids(case: ControlFlowBenchmarkCase) -> tuple[str, ...]:
    return tuple(
        _session_memory_node_id(case, index)
        for index, _memory in enumerate(case.session.memories)
    )


def _node(node_id, *, tags, content, created_at, updated_at, read_at):
    return MemoryNode(
        id=node_id,
        tags=tuple(tags),
        timestamps=MemoryTimestamps(
            created_at=_dt(created_at),
            updated_at=_dt(updated_at),
            read_at=None if read_at == "NONE" else _dt(read_at),
        ),
        content=content,
    )


def _session_node_id(case: ControlFlowBenchmarkCase) -> str:
    return "memory_node:" + _safe_id(case.session.id)


def _task_node_id(task_id: str) -> str:
    return "memory_node:" + _safe_id(task_id)


def _conversation_node_id(case: ControlFlowBenchmarkCase, index: int) -> str:
    return f"{_session_node_id(case)}_conversation_{index}"


def _message_node_id(
    case: ControlFlowBenchmarkCase,
    conversation_index: int,
    message_index: int,
) -> str:
    return f"{_conversation_node_id(case, conversation_index)}_message_{message_index}"


def _session_memory_node_id(case: ControlFlowBenchmarkCase, index: int) -> str:
    return f"{_session_node_id(case)}_memory_{index}"


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _dump_models(values: list[Any]) -> list[Any]:
    return [_dump_model(value) for value in values]


def _dump_model(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value
