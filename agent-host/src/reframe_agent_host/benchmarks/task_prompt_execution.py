from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from baml_bridge import Collector
from baml_sdk import benchmarks as baml_benchmarks
from baml_sdk import turn_context as baml_turn_context
from baml_sdk import task_catalog as baml_task_catalog
from baml_sdk import task as baml_task

from reframe_agent_host.agent_flow.machine_state import local_machine_state_context
from reframe_agent_host.agent_flow.provider_clients import client_kwargs
from reframe_agent_host.agent_flow.timestamps import timestamp_fields
from reframe_agent_host.benchmarks.reasoning_efforts import (
    collector_stop_reason,
    collector_usage,
)
from reframe_agent_host.memory_seed import ensure_core_tasks
from reframe_memory import MemoryDatabase, TaskNode


@dataclass(frozen=True)
class TaskPromptSnapshot:
    case: baml_benchmarks.TaskPromptBenchmarkCase
    current_timestamp: str
    selected_task: baml_task_catalog.SelectedTaskContext | None
    current_conversation: baml_turn_context.ConversationHistory
    session_memories: list[baml_turn_context.SessionMemoryContext]
    selected_memory_contexts: list[baml_task.TaskPromptSelectedMemoryContext]
    task_prompt_memories: list[baml_task.TaskPromptMemoryContext]
    latency_seconds: float
    error: str | None = None

    @property
    def selected_task_id(self) -> str | None:
        return self.selected_task.id if self.selected_task else None

    @property
    def selected_task_name(self) -> str | None:
        return self.selected_task.name if self.selected_task else None

    @property
    def task_correct(self) -> bool:
        return self.selected_task_name == self.case.expected_task_name


async def build_task_prompt_snapshot(
    database: MemoryDatabase,
    case: baml_benchmarks.TaskPromptBenchmarkCase,
    client=None,
    refresh: bool = False,
) -> TaskPromptSnapshot:
    del client, refresh
    started_at = time.perf_counter()
    timestamp = datetime.now(UTC).isoformat()
    conversation = baml_benchmarks.TaskPromptConversation(case, timestamp)
    session_memories = baml_benchmarks.TaskPromptSessionMemoryContexts(
        case,
        timestamp,
    )
    selected_memories = baml_benchmarks.TaskPromptSelectedMemoryContexts(
        case,
        timestamp,
    )
    task_prompt_memories = await _task_prompt_memories(database)
    try:
        task = _task_named(await _core_tasks(database), case.expected_task_name)
        selected_task = _selected_task_context(task)
        error = None
    except Exception as caught:
        selected_task = None
        error = str(caught)
    return TaskPromptSnapshot(
        case=case,
        current_timestamp=timestamp,
        selected_task=selected_task,
        current_conversation=conversation,
        session_memories=session_memories,
        selected_memory_contexts=selected_memories,
        task_prompt_memories=task_prompt_memories,
        latency_seconds=time.perf_counter() - started_at,
        error=error,
    )


async def run_task_prompt_case(
    client,
    provider,
    snapshot: TaskPromptSnapshot,
    run_index: int,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    collector = Collector(
        name=(
            f"task-prompt-{provider.id}-{reasoning_effort or 'default'}-"
            f"{snapshot.case.id}-{run_index}"
        )
    )
    if snapshot.error is not None:
        return {
            "case_id": snapshot.case.id,
            "run_index": run_index,
            "provider_id": provider.id,
            "reasoning_effort": reasoning_effort,
            "error": f"snapshot failed: {snapshot.error}",
            "snapshot_error": True,
            "latency_seconds": time.perf_counter() - started_at,
        }
    try:
        decision, latency = await task_prompt(client, snapshot)
    except Exception as error:
        return {
            "case_id": snapshot.case.id,
            "run_index": run_index,
            "provider_id": provider.id,
            "reasoning_effort": reasoning_effort,
            "error": str(error),
            "latency_seconds": time.perf_counter() - started_at,
            "usage": collector_usage(collector),
            "stop_reason": collector_stop_reason(collector),
        }
    evaluation = evaluate_task_prompt(decision, snapshot)
    return {
        "case_id": snapshot.case.id,
        "run_index": run_index,
        "provider_id": provider.id,
        "reasoning_effort": reasoning_effort,
        "selected_task_id": snapshot.selected_task_id,
        "selected_task_name": snapshot.selected_task_name,
        "task_correct": snapshot.task_correct,
        "decision": decision.model_dump(mode="json"),
        **evaluation,
        "latency_seconds": latency,
        "stage_latency_seconds": {"task_prompt": latency},
        "usage": collector_usage(collector),
        "stop_reason": collector_stop_reason(collector),
    }


async def warmup_task_prompt(client, snapshots, config) -> int:
    usable = [snapshot for snapshot in snapshots if snapshot.error is None]
    if not usable:
        return 0
    errors = 0
    for _ in range(config.warmup_runs):
        try:
            await task_prompt(client, usable[0])
        except Exception:
            errors += 1
        if config.delay_seconds > 0:
            await asyncio.sleep(config.delay_seconds)
    return errors


async def task_prompt(client, snapshot: TaskPromptSnapshot):
    if snapshot.selected_task is None:
        raise ValueError("task prompt snapshot has no selected task")
    started_at = time.perf_counter()
    composition = await baml_task.ComposeTaskInput_async(
        current_user_request=snapshot.case.current_user_request,
        current_conversation=snapshot.current_conversation,
        session_memories=snapshot.session_memories,
        selected_task=snapshot.selected_task,
        selected_memories=snapshot.selected_memory_contexts,
        task_prompt_memories=snapshot.task_prompt_memories,
        machine_state=local_machine_state_context("Benchmark machine state"),
        **client_kwargs(client),
    )
    decision = await baml_task.PromptDecision_async(
        snapshot.selected_task.prompt,
        composition,
    )
    return decision, time.perf_counter() - started_at


def evaluate_task_prompt(
    decision: baml_task.TaskPromptDecision,
    snapshot: TaskPromptSnapshot,
) -> dict[str, Any]:
    del snapshot
    evaluation = baml_benchmarks.EvaluateTaskPrompt(decision.full_task_prompt)
    result = evaluation.model_dump(mode="json")
    result["structural_pass"] = evaluation.correct
    return result


def snapshot_payload(snapshot: TaskPromptSnapshot) -> dict[str, Any]:
    payload = {
        "case_id": snapshot.case.id,
        "current_timestamp": snapshot.current_timestamp,
        "current_user_request": snapshot.case.current_user_request,
        "expected_task_name": snapshot.case.expected_task_name,
        "selected_task_id": snapshot.selected_task_id,
        "selected_task_name": snapshot.selected_task_name,
        "task_correct": snapshot.task_correct,
        "latency_seconds": snapshot.latency_seconds,
        "task_prompt_input_snapshot": {
            "selected_task": _dump_model(snapshot.selected_task),
            "current_conversation": _dump_model(snapshot.current_conversation),
            "session_memories": _dump_models(snapshot.session_memories),
            "selected_memories": _dump_models(snapshot.selected_memory_contexts),
            "task_prompt_memories": _dump_models(snapshot.task_prompt_memories),
        },
    }
    if snapshot.error is not None:
        payload["error"] = snapshot.error
    return payload


async def _core_tasks(database: MemoryDatabase) -> list[TaskNode]:
    seed = await ensure_core_tasks(database)
    tasks = []
    seen = set()
    for provider_id in seed.provider_ids:
        for task in await database.providers.tasks_for(provider_id):
            if task.id not in seen:
                seen.add(task.id)
                tasks.append(task)
    return tasks


def _task_named(tasks: list[TaskNode], name: str) -> TaskNode:
    for task in tasks:
        if task.content.name == name:
            return task
    raise ValueError(f"benchmark task not found: {name}")


def _selected_task_context(task: TaskNode) -> baml_task_catalog.SelectedTaskContext:
    return baml_task_catalog.SelectedTaskContext(
        id=task.id,
        name=task.content.name,
        description=task.content.description,
        input=task.content.input,
        output=task.content.output,
        prompt=task.content.prompt,
        provider_id=task.content.provider_id,
        **timestamp_fields(task),
    )


async def _task_prompt_memories(
    database: MemoryDatabase,
) -> list[baml_task.TaskPromptMemoryContext]:
    memories = await database.task_prompt_memories.search()
    return [
        baml_task.TaskPromptMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in memories
    ]


def _dump_models(values: list[Any]) -> list[Any]:
    return [_dump_model(value) for value in values]


def _dump_model(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value
