from __future__ import annotations

import time
from typing import Any

from baml_core import Collector
from baml_sdk import benchmarks as baml_benchmarks
from baml_sdk import memory_search as baml_memory_search
from baml_sdk import task_routing as baml_task_routing

from reframe_agent_host.agent_flow.machine_state import local_machine_state_context
from reframe_agent_host.agent_flow.provider_clients import client_kwargs
from reframe_agent_host.benchmarks.config import BenchmarkConfig
from reframe_agent_host.benchmarks.control_flow_execution import (
    ControlFlowSnapshot,
    run_search_depth_case,
    search_depths,
    warmup_search_depth,
)
from reframe_agent_host.benchmarks.memory_relevance_execution import (
    MemoryRelevanceSnapshot,
    relevant_memories,
    run_memory_relevance_case,
    warmup_memory_relevance,
)
from reframe_agent_host.benchmarks.model_matrix import (
    benchmark_provider,
    discover_efforts,
    warmup as run_warmup,
)
from reframe_agent_host.benchmarks.reasoning_efforts import (
    collector_stop_reason,
    collector_usage,
)
from reframe_agent_host.benchmarks.task_prompt_execution import (
    TaskPromptSnapshot,
    run_task_prompt_case,
    task_prompt,
    warmup_task_prompt,
)
from reframe_memory import ProviderNode


async def discover_control_flow_reasoning_efforts(
    provider: ProviderNode,
    snapshots: tuple[ControlFlowSnapshot, ...],
    config: BenchmarkConfig,
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    usable = tuple(snapshot for snapshot in snapshots if snapshot.error is None)
    return await discover_efforts(
        provider,
        config,
        "search-depth",
        (lambda client: search_depths(client, usable[0])) if usable else None,
    )


async def benchmark_control_flow_provider(
    provider: ProviderNode,
    snapshots: tuple[ControlFlowSnapshot, ...],
    config: BenchmarkConfig,
    effort: str,
) -> dict[str, Any]:
    return await benchmark_provider(
        provider,
        snapshots,
        config,
        effort,
        run_search_depth_case,
        lambda client: warmup_search_depth(client, snapshots, config),
        correct_key="task_correct",
    )


async def discover_memory_relevance_reasoning_efforts(
    provider: ProviderNode,
    snapshots: tuple[MemoryRelevanceSnapshot, ...],
    config: BenchmarkConfig,
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    usable = tuple(snapshot for snapshot in snapshots if snapshot.error is None)
    return await discover_efforts(
        provider,
        config,
        "memory-relevance",
        (lambda client: relevant_memories(client, usable[0])) if usable else None,
    )


async def benchmark_memory_relevance_provider(
    provider: ProviderNode,
    snapshots: tuple[MemoryRelevanceSnapshot, ...],
    config: BenchmarkConfig,
    effort: str,
) -> dict[str, Any]:
    return await benchmark_provider(
        provider,
        snapshots,
        config,
        effort,
        run_memory_relevance_case,
        lambda client: warmup_memory_relevance(client, snapshots, config),
    )


async def discover_task_prompt_reasoning_efforts(
    provider: ProviderNode,
    snapshots: tuple[TaskPromptSnapshot, ...],
    config: BenchmarkConfig,
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    usable = tuple(snapshot for snapshot in snapshots if snapshot.error is None)
    return await discover_efforts(
        provider,
        config,
        "task-prompt",
        (lambda client: task_prompt(client, usable[0])) if usable else None,
    )


async def benchmark_task_prompt_provider(
    provider: ProviderNode,
    snapshots: tuple[TaskPromptSnapshot, ...],
    config: BenchmarkConfig,
    effort: str,
) -> dict[str, Any]:
    return await benchmark_provider(
        provider,
        snapshots,
        config,
        effort,
        run_task_prompt_case,
        lambda client: warmup_task_prompt(client, snapshots, config),
    )


async def discover_task_choice_reasoning_efforts(
    provider: ProviderNode,
    cases: tuple[baml_benchmarks.TaskChoiceBenchmarkCase, ...],
    context: Any,
    config: BenchmarkConfig,
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    probe = None
    if cases:
        probe = lambda client: _choose_task(client, cases[0].transcript, context)
    return await discover_efforts(provider, config, "task-choice", probe)


async def benchmark_task_choice_provider(
    provider: ProviderNode,
    cases: tuple[baml_benchmarks.TaskChoiceBenchmarkCase, ...],
    expected_task_ids: dict[str, str],
    task_names: dict[str, str],
    context: Any,
    config: BenchmarkConfig,
    effort: str,
) -> dict[str, Any]:
    async def run_case(client, run_provider, case, run_index, reasoning_effort):
        started_at = time.perf_counter()
        collector = Collector(
            name=f"task-choice-{run_provider.id}-{reasoning_effort}-{case.id}-{run_index}"
        )
        try:
            decision = await _choose_task(client, case.transcript, context)
        except Exception as error:
            return _error_result(
                case.id,
                run_index,
                run_provider,
                reasoning_effort,
                error,
                started_at,
                collector,
            )
        expected_task_id = expected_task_ids[case.expected_task_name]
        return {
            "case_id": case.id,
            "run_index": run_index,
            "provider_id": run_provider.id,
            "reasoning_effort": reasoning_effort,
            "expected_task_id": expected_task_id,
            "expected_task_name": case.expected_task_name,
            "selected_task_id": decision.selected_task_id,
            "selected_task_name": task_names.get(decision.selected_task_id),
            "correct": baml_benchmarks.TaskChoiceCorrect(
                decision,
                expected_task_id,
            ),
            "confidence": decision.confidence,
            "latency_seconds": time.perf_counter() - started_at,
            "usage": collector_usage(collector),
            "stop_reason": collector_stop_reason(collector),
        }

    async def warmup(client):
        return await run_warmup(
            config,
            lambda: _choose_task(client, cases[0].transcript, context),
        )

    return await benchmark_provider(
        provider,
        cases,
        config,
        effort,
        run_case,
        warmup,
    )


async def discover_conversation_evaluation_reasoning_efforts(
    provider: ProviderNode,
    cases: tuple[baml_benchmarks.ConversationEvaluationBenchmarkCase, ...],
    config: BenchmarkConfig,
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    probe = None
    if cases:
        probe = lambda client: _choose_memory_search(client, cases[0])
    return await discover_efforts(
        provider,
        config,
        "conversation-evaluation",
        probe,
    )


async def benchmark_conversation_evaluation_provider(
    provider: ProviderNode,
    cases: tuple[baml_benchmarks.ConversationEvaluationBenchmarkCase, ...],
    config: BenchmarkConfig,
    effort: str,
) -> dict[str, Any]:
    async def run_case(client, run_provider, case, run_index, reasoning_effort):
        started_at = time.perf_counter()
        collector = Collector(
            name=(
                f"conversation-evaluation-{run_provider.id}-"
                f"{reasoning_effort}-{case.id}-{run_index}"
            )
        )
        try:
            hints = await _choose_memory_search(client, case)
        except Exception as error:
            return _error_result(
                case.id,
                run_index,
                run_provider,
                reasoning_effort,
                error,
                started_at,
                collector,
            )
        return {
            "case_id": case.id,
            "run_index": run_index,
            "provider_id": run_provider.id,
            "reasoning_effort": reasoning_effort,
            "hints": hints.model_dump(mode="json"),
            "latency_seconds": time.perf_counter() - started_at,
            "usage": collector_usage(collector),
            "stop_reason": collector_stop_reason(collector),
        }

    async def warmup(client):
        return await run_warmup(
            config,
            lambda: _choose_memory_search(client, cases[0]),
        )

    return await benchmark_provider(
        provider,
        cases,
        config,
        effort,
        run_case,
        warmup,
        include_correct=False,
    )


async def _choose_task(client: Any, transcript: str, context: Any):
    return await baml_task_routing.ChooseTask_async(
        current_user_request=transcript,
        current_conversation=context.current_conversation,
        session_memories=context.session_memories,
        user_preferences=context.user_preferences,
        available_tasks=context.available_tasks,
        task_choice_memories=context.task_choice_memories,
        machine_state=local_machine_state_context("Benchmark machine state"),
        **client_kwargs(client),
    )


async def _choose_memory_search(client: Any, case: Any):
    conversations = baml_benchmarks.ConversationContexts(case.session_conversations)
    return await baml_memory_search.ChooseMemorySearch_async(
        current_user_request=case.current_user_request,
        current_conversation=conversations[0] if conversations else None,
        session_memories=baml_benchmarks.SessionMemoryContexts(
            case.session_memories
        ),
        selected_task=baml_benchmarks.SelectedTaskContext(case.selected_task),
        conversation_evaluation_memories=baml_benchmarks.ConversationEvaluationMemoryContexts(
            case.conversation_evaluation_memories
        ),
        machine_state=local_machine_state_context("Benchmark machine state"),
        **client_kwargs(client),
    )


def _error_result(
    case_id: str,
    run_index: int,
    provider: ProviderNode,
    effort: str,
    error: Exception,
    started_at: float,
    collector: Collector,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "run_index": run_index,
        "provider_id": provider.id,
        "reasoning_effort": effort,
        "error": str(error),
        "latency_seconds": time.perf_counter() - started_at,
        "usage": collector_usage(collector),
        "stop_reason": collector_stop_reason(collector),
    }
