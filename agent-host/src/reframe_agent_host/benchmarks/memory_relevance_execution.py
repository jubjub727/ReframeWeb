from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from typing import Any

from baml_core import Collector
from baml_sdk import benchmarks as baml_benchmarks
from baml_sdk import context as baml_context
from baml_sdk import memory_selection as baml_memory_selection
from baml_sdk import task_routing as baml_task_routing

from reframe_agent_host.agent_flow.machine_state import local_machine_state_context
from reframe_agent_host.agent_flow.provider_clients import client_kwargs
from reframe_agent_host.benchmarks.reasoning_efforts import (
    collector_stop_reason,
    collector_usage,
)


@dataclass(frozen=True)
class MemoryRelevanceSnapshot:
    case: baml_benchmarks.ControlFlowBenchmarkCase
    selected_task: baml_task_routing.SelectedTaskContext
    current_conversation: baml_context.ConversationHistory | None
    session_memories: list[baml_context.SessionMemoryContext]
    candidate_memories: list[baml_memory_selection.RetrievedMemoryCandidate]
    expected_kept_memory_ids: tuple[str, ...]
    relevance_memories: list[baml_memory_selection.RelevanceMemoryContext]
    latency_seconds: float
    error: str | None = None

    @property
    def selected_task_id(self) -> str:
        return self.selected_task.id

    @property
    def task_correct(self) -> bool:
        return self.selected_task_id == self.case.expected_task_id


async def build_memory_relevance_snapshot(
    case: baml_benchmarks.ControlFlowBenchmarkCase,
    client=None,
) -> MemoryRelevanceSnapshot:
    del client
    started_at = time.perf_counter()
    conversations = baml_benchmarks.ConversationContexts(case.session.conversations)
    return MemoryRelevanceSnapshot(
        case=case,
        selected_task=baml_benchmarks.MemoryRelevanceSelectedTask(case),
        current_conversation=conversations[0] if conversations else None,
        session_memories=baml_benchmarks.SessionMemoryContexts(case.session.memories),
        candidate_memories=baml_benchmarks.MemoryRelevanceCandidates(case),
        expected_kept_memory_ids=tuple(
            baml_benchmarks.MemoryRelevanceExpectedIds(case)
        ),
        relevance_memories=[],
        latency_seconds=time.perf_counter() - started_at,
    )


async def run_memory_relevance_case(
    client,
    provider,
    snapshot: MemoryRelevanceSnapshot,
    run_index: int,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    collector = Collector(
        name=(
            f"memory-relevance-{provider.id}-{reasoning_effort or 'default'}-"
            f"{snapshot.case.id}-{run_index}"
        )
    )
    if snapshot.error is not None:
        return _error_result(
            provider.id,
            snapshot,
            run_index,
            reasoning_effort,
            f"snapshot failed: {snapshot.error}",
            started_at,
            snapshot_error=True,
        )
    try:
        decision, latency = await relevant_memories(client, snapshot)
    except Exception as error:
        result = _error_result(
            provider.id,
            snapshot,
            run_index,
            reasoning_effort,
            str(error),
            started_at,
        )
        result.update(
            usage=collector_usage(collector),
            stop_reason=collector_stop_reason(collector),
        )
        return result

    expected_ids = list(snapshot.expected_kept_memory_ids)
    return {
        "case_id": snapshot.case.id,
        "run_index": run_index,
        "provider_id": provider.id,
        "reasoning_effort": reasoning_effort,
        "expected_kept_memory_ids": expected_ids,
        "kept_memory_ids": list(decision.kept_memory_ids),
        "correct": baml_benchmarks.MemorySelectionCorrect(decision, expected_ids),
        "selected_task_id": snapshot.selected_task_id,
        "task_correct": snapshot.task_correct,
        "decision": decision.model_dump(mode="json"),
        "latency_seconds": latency,
        "stage_latency_seconds": {"memory_relevance": latency},
        "usage": collector_usage(collector),
        "stop_reason": collector_stop_reason(collector),
    }


async def warmup_memory_relevance(client, snapshots, config) -> int:
    usable = [snapshot for snapshot in snapshots if snapshot.error is None]
    if config.warmup_runs < 1 or not usable:
        return 0
    errors = 0
    for _ in range(config.warmup_runs):
        try:
            await relevant_memories(client, usable[0])
        except Exception:
            errors += 1
        if config.delay_seconds > 0:
            await asyncio.sleep(config.delay_seconds)
    return errors


async def relevant_memories(client, snapshot: MemoryRelevanceSnapshot):
    started_at = time.perf_counter()
    result = await baml_memory_selection.SelectRelevantMemories_async(
        current_user_request=snapshot.case.current_user_request,
        current_conversation=snapshot.current_conversation,
        session_memories=snapshot.session_memories,
        selected_task=snapshot.selected_task,
        candidate_memories=snapshot.candidate_memories,
        relevance_memories=snapshot.relevance_memories,
        machine_state=local_machine_state_context("Benchmark machine state"),
        **client_kwargs(client),
    )
    return result, time.perf_counter() - started_at


def snapshot_payload(snapshot: MemoryRelevanceSnapshot) -> dict[str, Any]:
    payload = {
        "case_id": snapshot.case.id,
        "current_user_request": snapshot.case.current_user_request,
        "expected_task_id": snapshot.case.expected_task_id,
        "selected_task_id": snapshot.selected_task_id,
        "task_correct": snapshot.task_correct,
        "expected_kept_memory_ids": list(snapshot.expected_kept_memory_ids),
        "latency_seconds": snapshot.latency_seconds,
        "relevance_input_snapshot": {
            "current_conversation": _dump(snapshot.current_conversation),
            "session_memories": _dump_each(snapshot.session_memories),
            "selected_task": _dump(snapshot.selected_task),
            "candidate_memories": _dump_each(snapshot.candidate_memories),
            "relevance_memories": _dump_each(snapshot.relevance_memories),
        },
    }
    if snapshot.error is not None:
        payload["error"] = snapshot.error
    return payload


def _error_result(
    provider_id,
    snapshot,
    run_index,
    reasoning_effort,
    error,
    started_at,
    snapshot_error=False,
):
    return {
        "case_id": snapshot.case.id,
        "run_index": run_index,
        "provider_id": provider_id,
        "reasoning_effort": reasoning_effort,
        "expected_kept_memory_ids": list(snapshot.expected_kept_memory_ids),
        "selected_task_id": snapshot.selected_task_id,
        "task_correct": snapshot.task_correct,
        "snapshot_error": snapshot_error,
        "error": error,
        "latency_seconds": time.perf_counter() - started_at,
    }


def _dump_each(values) -> list[Any]:
    return [_dump(value) for value in values]


def _dump(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value
