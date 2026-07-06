from __future__ import annotations

import asyncio
import time
from typing import Any

from baml_core import Collector

import baml_sdk as baml
from reframe_agent_host.agent_flow.baml_clients import client_kwargs
from reframe_agent_host.benchmarks.reasoning_efforts import (
    collector_stop_reason,
    collector_usage,
    opencode_reasoning_effort_client,
    unsupported_reasoning_effort_error,
)
from reframe_agent_host.benchmarks.task_choice_cases import TaskChoiceBenchmarkCase
from reframe_agent_host.benchmarks.task_choice_config import TaskChoiceBenchmarkConfig
from reframe_agent_host.benchmarks.task_choice_provider_index import model_id_for_surface
from reframe_agent_host.benchmarks.task_choice_stats import latency_summary
from reframe_memory import ProviderNode


async def discover_task_choice_reasoning_efforts(
    provider: ProviderNode,
    cases: tuple[TaskChoiceBenchmarkCase, ...],
    context,
    config: TaskChoiceBenchmarkConfig,
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    if config.reasoning_efforts:
        return config.reasoning_efforts, [
            _discovery_result(provider, effort, supported=True, source="configured")
            for effort in config.reasoning_efforts
        ]

    supported = []
    results = []
    for effort in config.reasoning_effort_candidates:
        result = await _probe_task_choice_reasoning_effort(
            provider,
            cases,
            context,
            effort,
        )
        results.append(result)
        if result["supported"]:
            supported.append(effort)
    return tuple(supported), results


async def benchmark_provider(
    provider: ProviderNode,
    cases: tuple[TaskChoiceBenchmarkCase, ...],
    expected_task_ids: dict[str, str],
    task_names: dict[str, str],
    context,
    config: TaskChoiceBenchmarkConfig,
    reasoning_effort: str,
) -> dict[str, Any]:
    client, benchmark_client = opencode_reasoning_effort_client(
        provider,
        reasoning_effort,
    )
    warmup_errors = await _warmup(client, cases, context, config)
    results = []
    latencies = []
    correct_count = 0
    error_count = 0

    for case in cases:
        for run_index in range(config.runs):
            result = await _run_case(
                client,
                provider,
                case,
                expected_task_ids[case.expected_task_name],
                task_names,
                run_index,
                context,
                reasoning_effort,
            )
            results.append(result)
            if "latency_seconds" in result:
                latencies.append(result["latency_seconds"])
            if result.get("correct") is True:
                correct_count += 1
            if "error" in result:
                error_count += 1
            if config.delay_seconds > 0:
                await asyncio.sleep(config.delay_seconds)

    total = len(cases) * config.runs
    return {
        "provider_id": provider.id,
        "provider_name": provider.content.name,
        "baml_surface": provider.content.baml_surface,
        "base_baml_surface": provider.content.baml_surface,
        "benchmark_client": benchmark_client,
        "model_id": model_id_for_surface(provider.content.baml_surface),
        "reasoning_effort": reasoning_effort,
        "total": total,
        "correct": correct_count,
        "errors": error_count,
        "warmup_errors": warmup_errors,
        "accuracy": correct_count / total if total else 0.0,
        "latency_seconds": latency_summary(latencies),
        "case_results": results,
    }


async def _probe_task_choice_reasoning_effort(
    provider: ProviderNode,
    cases: tuple[TaskChoiceBenchmarkCase, ...],
    context,
    effort: str,
) -> dict[str, Any]:
    if not cases:
        return _discovery_result(provider, effort, supported=False, error="no cases")

    client, benchmark_client = opencode_reasoning_effort_client(
        provider,
        effort,
    )
    collector = Collector(name=f"task-choice-discovery-{provider.id}-{effort}")
    started_at = time.perf_counter()
    try:
        await baml.ChooseInitialTask_async(
            current_user_request=cases[0].transcript,
            current_conversation=context.current_conversation,
            session_memories=context.session_memories,
            available_tasks=context.available_tasks,
            task_choice_memories=context.task_choice_memories,
            **client_kwargs(client),
        )
    except Exception as exc:
        supported = not unsupported_reasoning_effort_error(exc)
        return _discovery_result(
            provider,
            effort,
            supported=supported,
            benchmark_client=benchmark_client,
            error=str(exc),
            latency_seconds=time.perf_counter() - started_at,
            usage=collector_usage(collector),
            stop_reason=collector_stop_reason(collector),
        )

    return _discovery_result(
        provider,
        effort,
        supported=True,
        benchmark_client=benchmark_client,
        latency_seconds=time.perf_counter() - started_at,
        usage=collector_usage(collector),
        stop_reason=collector_stop_reason(collector),
    )


async def _run_case(
    client,
    provider: ProviderNode,
    case: TaskChoiceBenchmarkCase,
    expected_task_id: str,
    task_names: dict[str, str],
    run_index: int,
    context,
    reasoning_effort: str,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    collector = Collector(
        name=f"task-choice-{provider.id}-{reasoning_effort}-{case.id}-{run_index}"
    )
    try:
        decision = await baml.ChooseInitialTask_async(
            current_user_request=case.transcript,
            current_conversation=context.current_conversation,
            session_memories=context.session_memories,
            available_tasks=context.available_tasks,
            task_choice_memories=context.task_choice_memories,
            **client_kwargs(client),
        )
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

    selected_name = task_names.get(decision.selected_task_id)
    return {
        "case_id": case.id,
        "run_index": run_index,
        "provider_id": provider.id,
        "reasoning_effort": reasoning_effort,
        "expected_task_id": expected_task_id,
        "expected_task_name": case.expected_task_name,
        "selected_task_id": decision.selected_task_id,
        "selected_task_name": selected_name,
        "correct": decision.selected_task_id == expected_task_id,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "latency_seconds": time.perf_counter() - started_at,
        "usage": collector_usage(collector),
        "stop_reason": collector_stop_reason(collector),
    }


async def _warmup(client, cases, context, config: TaskChoiceBenchmarkConfig) -> int:
    errors = 0
    if config.warmup_runs < 1:
        return errors

    for _ in range(config.warmup_runs):
        try:
            await baml.ChooseInitialTask_async(
                current_user_request=cases[0].transcript,
                current_conversation=context.current_conversation,
                session_memories=context.session_memories,
                available_tasks=context.available_tasks,
                task_choice_memories=context.task_choice_memories,
                **client_kwargs(client),
            )
        except Exception:
            errors += 1
        if config.delay_seconds > 0:
            await asyncio.sleep(config.delay_seconds)
    return errors


def _discovery_result(
    provider: ProviderNode,
    effort: str,
    *,
    supported: bool,
    source: str = "probe",
    benchmark_client: str | None = None,
    error: str | None = None,
    latency_seconds: float | None = None,
    usage: dict[str, int | None] | None = None,
    stop_reason: str | None = None,
) -> dict[str, Any]:
    result = {
        "provider_id": provider.id,
        "provider_name": provider.content.name,
        "baml_surface": provider.content.baml_surface,
        "model_id": model_id_for_surface(provider.content.baml_surface),
        "reasoning_effort": effort,
        "supported": supported,
        "source": source,
    }
    if benchmark_client is not None:
        result["benchmark_client"] = benchmark_client
    if error is not None:
        result["error"] = error
    if latency_seconds is not None:
        result["latency_seconds"] = latency_seconds
    if usage is not None:
        result["usage"] = usage
    if stop_reason is not None:
        result["stop_reason"] = stop_reason
    return result
