from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from typing import Any

from baml_core import Collector

from reframe_agent_host.agent_flow.search_depth import default_search_domains
import baml_sdk as baml
from reframe_agent_host.agent_flow.baml_clients import client_kwargs
from reframe_agent_host.benchmarks.control_flow_case_types import (
    ControlFlowBenchmarkCase,
)
from reframe_agent_host.benchmarks.control_flow_config import (
    ControlFlowBenchmarkConfig,
)
from reframe_agent_host.benchmarks.control_flow_context import (
    available_task_context,
    case_conversation_context,
    case_session_memory_context,
    search_depth_memory_context,
    selected_task_from_case,
    task_choice_memory_context,
)
from reframe_agent_host.benchmarks.control_flow_time import cutoff_age
from reframe_agent_host.benchmarks.conversation_evaluation_context import (
    conversation_evaluation_memory_context,
)
from reframe_agent_host.benchmarks.reasoning_efforts import (
    collector_stop_reason,
    collector_usage,
)
from reframe_memory import ProviderNode


@dataclass(frozen=True)
class ControlFlowSnapshot:
    case: ControlFlowBenchmarkCase
    task_choice: Any | None
    selected_task: Any | None
    search_hints: Any | None
    session_conversations: list[Any]
    session_memories: list[Any]
    search_domains: list[Any]
    search_depth_memories: list[Any]
    latency_seconds: float
    stage_latency_seconds: dict[str, float]
    error: str | None = None

    @property
    def selected_task_id(self) -> str | None:
        if self.task_choice is None:
            return None
        return self.task_choice.selected_task_id

    @property
    def task_correct(self) -> bool:
        return self.selected_task_id == self.case.expected_task_id


async def build_control_flow_snapshot(
    case: ControlFlowBenchmarkCase,
    client=None,
) -> ControlFlowSnapshot:
    total_started_at = time.perf_counter()
    stage_latencies: dict[str, float] = {}
    task_choice = None
    selected_task = None
    hints = None
    session_conversations = case_conversation_context(case)
    session_memories = case_session_memory_context(case)
    search_domains = default_search_domains()
    search_depth_memories = search_depth_memory_context(case.search_depth_memories)

    try:
        task_choice, task_choice_latency = await choose_task(client, case)
        stage_latencies["task_choice"] = task_choice_latency
        selected_task = selected_task_from_case(case, task_choice.selected_task_id)
        hints, hints_latency = await search_hints(
            client,
            case,
            selected_task,
        )
        stage_latencies["search_hints"] = hints_latency
    except Exception as exc:
        return ControlFlowSnapshot(
            case=case,
            task_choice=task_choice,
            selected_task=selected_task,
            search_hints=hints,
            session_conversations=session_conversations,
            session_memories=session_memories,
            search_domains=search_domains,
            search_depth_memories=search_depth_memories,
            latency_seconds=time.perf_counter() - total_started_at,
            stage_latency_seconds=stage_latencies,
            error=str(exc),
        )

    return ControlFlowSnapshot(
        case=case,
        task_choice=task_choice,
        selected_task=selected_task,
        search_hints=hints,
        session_conversations=session_conversations,
        session_memories=session_memories,
        search_domains=search_domains,
        search_depth_memories=search_depth_memories,
        latency_seconds=time.perf_counter() - total_started_at,
        stage_latency_seconds=stage_latencies,
    )


async def run_search_depth_case(
    client,
    provider: ProviderNode,
    snapshot: ControlFlowSnapshot,
    run_index: int,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    case = snapshot.case
    collector = Collector(
        name=(
            f"search-depth-{provider.id}-{reasoning_effort or 'default'}-"
            f"{case.id}-{run_index}"
        )
    )
    if snapshot.error is not None:
        return {
            "case_id": case.id,
            "run_index": run_index,
            "provider_id": provider.id,
            "reasoning_effort": reasoning_effort,
            "current_timestamp": case.current_timestamp,
            "expected_task_id": case.expected_task_id,
            "selected_task_id": snapshot.selected_task_id,
            "task_correct": snapshot.task_correct,
            "snapshot_error": True,
            "error": f"snapshot failed: {snapshot.error}",
            "latency_seconds": time.perf_counter() - started_at,
        }

    try:
        depths, depth_latency = await search_depths(client, snapshot)
    except Exception as exc:
        return {
            "case_id": case.id,
            "run_index": run_index,
            "provider_id": provider.id,
            "reasoning_effort": reasoning_effort,
            "error": str(exc),
            "latency_seconds": time.perf_counter() - started_at,
            "usage": collector_usage(collector),
            "stop_reason": collector_stop_reason(collector),
        }

    return {
        "case_id": case.id,
        "run_index": run_index,
        "provider_id": provider.id,
        "reasoning_effort": reasoning_effort,
        "current_timestamp": case.current_timestamp,
        "expected_task_id": case.expected_task_id,
        "selected_task_id": snapshot.selected_task_id,
        "task_correct": snapshot.task_correct,
        "search_depths": depths.model_dump(mode="json"),
        "search_depth_ages": depth_ages(case.current_timestamp, depths.depths),
        "latency_seconds": depth_latency,
        "stage_latency_seconds": {"search_depth": depth_latency},
        "usage": collector_usage(collector),
        "stop_reason": collector_stop_reason(collector),
    }


async def warmup_search_depth(
    client,
    snapshots,
    config: ControlFlowBenchmarkConfig,
) -> int:
    errors = 0
    usable_snapshots = [snapshot for snapshot in snapshots if snapshot.error is None]
    if config.warmup_runs < 1 or not usable_snapshots:
        return errors

    for _ in range(config.warmup_runs):
        try:
            await search_depths(client, usable_snapshots[0])
        except Exception:
            errors += 1
        if config.delay_seconds > 0:
            await asyncio.sleep(config.delay_seconds)
    return errors


async def choose_task(client, case: ControlFlowBenchmarkCase):
    started_at = time.perf_counter()
    result = await baml.ChooseTask_async(
        current_user_request=case.current_user_request,
        current_conversation=_current_conversation(case_conversation_context(case)),
        session_memories=case_session_memory_context(case),
        available_tasks=available_task_context(case.available_tasks),
        task_choice_memories=task_choice_memory_context(case.task_choice_memories),
        **client_kwargs(client),
    )
    return result, time.perf_counter() - started_at


def _current_conversation(conversations):
    return conversations[0] if conversations else None


async def search_hints(client, case: ControlFlowBenchmarkCase, selected_task):
    started_at = time.perf_counter()
    result = await baml.ChooseMemorySearch_async(
        current_user_request=case.current_user_request,
        current_conversation=_current_conversation(case_conversation_context(case)),
        session_memories=case_session_memory_context(case),
        selected_task=selected_task,
        conversation_evaluation_memories=conversation_evaluation_memory_context(
            case.conversation_evaluation_memories
        ),
        **client_kwargs(client),
    )
    return result, time.perf_counter() - started_at


async def search_depths(
    client,
    snapshot: ControlFlowSnapshot,
):
    started_at = time.perf_counter()
    result = await baml.ChooseMemorySearchDepths_async(
        current_timestamp=snapshot.case.current_timestamp,
        current_user_request=snapshot.case.current_user_request,
        current_conversation=_current_conversation(snapshot.session_conversations),
        session_memories=snapshot.session_memories,
        selected_task=snapshot.selected_task,
        memory_search_hints=snapshot.search_hints,
        search_domains=snapshot.search_domains,
        search_depth_memories=snapshot.search_depth_memories,
        **client_kwargs(client),
    )
    return result, time.perf_counter() - started_at


def depth_ages(current_timestamp: str, depths) -> dict[str, dict[str, object]]:
    return {
        domain: {
            field: cutoff_age(current_timestamp, timestamp)
            for field, timestamp in timestamps.model_dump(mode="json").items()
        }
        for domain, timestamps in depths.items()
    }


def snapshot_payload(snapshot: ControlFlowSnapshot) -> dict[str, Any]:
    payload = {
        "case_id": snapshot.case.id,
        "current_timestamp": snapshot.case.current_timestamp,
        "current_user_request": snapshot.case.current_user_request,
        "expected_task_id": snapshot.case.expected_task_id,
        "selected_task_id": snapshot.selected_task_id,
        "task_correct": snapshot.task_correct,
        "latency_seconds": snapshot.latency_seconds,
        "stage_latency_seconds": dict(snapshot.stage_latency_seconds),
        "task_choice": _dump_model(snapshot.task_choice),
        "search_hints": _dump_model(snapshot.search_hints),
        "search_depth_input_snapshot": {
            "session": _session_payload(snapshot.case),
            "current_conversation": _dump_model(
                _current_conversation(snapshot.session_conversations)
            ),
            "session_memories": _dump_models(snapshot.session_memories),
            "selected_task": _dump_model(snapshot.selected_task),
            "memory_search_hints": _dump_model(snapshot.search_hints),
            "search_domains": _dump_models(snapshot.search_domains),
            "search_depth_memories": _dump_models(snapshot.search_depth_memories),
        },
    }
    if snapshot.error is not None:
        payload["error"] = snapshot.error
    return payload


def _session_payload(case: ControlFlowBenchmarkCase) -> dict[str, str]:
    return {
        "id": case.session.id,
        "name": case.session.name,
        "created_at": case.session.created_at,
        "updated_at": case.session.updated_at,
        "read_at": case.session.read_at,
    }


def _dump_models(values: list[Any]) -> list[Any]:
    return [_dump_model(value) for value in values]


def _dump_model(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value
