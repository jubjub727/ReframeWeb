from __future__ import annotations

import asyncio
import time
from typing import Any

from reframe_agent_host.baml_client import b
from reframe_agent_host.benchmarks.task_choice_cases import TaskChoiceBenchmarkCase
from reframe_agent_host.benchmarks.task_choice_config import TaskChoiceBenchmarkConfig
from reframe_agent_host.benchmarks.task_choice_provider_index import model_id_for_surface
from reframe_agent_host.benchmarks.task_choice_stats import latency_summary
from reframe_memory import ProviderNode


async def benchmark_provider(
    provider: ProviderNode,
    cases: tuple[TaskChoiceBenchmarkCase, ...],
    expected_task_ids: dict[str, str],
    task_names: dict[str, str],
    context,
    config: TaskChoiceBenchmarkConfig,
) -> dict[str, Any]:
    client = b.with_options(client=provider.content.baml_surface)
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
        "model_id": model_id_for_surface(provider.content.baml_surface),
        "total": total,
        "correct": correct_count,
        "errors": error_count,
        "warmup_errors": warmup_errors,
        "accuracy": correct_count / total if total else 0.0,
        "latency_seconds": latency_summary(latencies),
        "case_results": results,
    }


async def _run_case(
    client,
    provider: ProviderNode,
    case: TaskChoiceBenchmarkCase,
    expected_task_id: str,
    task_names: dict[str, str],
    run_index: int,
    context,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        decision = await client.ChooseInitialTask(
            current_user_request=case.transcript,
            session_conversations=context.session_conversations,
            session_memories=context.session_memories,
            available_tasks=context.available_tasks,
            task_choice_memories=context.task_choice_memories,
        )
    except Exception as exc:
        return {
            "case_id": case.id,
            "run_index": run_index,
            "provider_id": provider.id,
            "error": str(exc),
            "latency_seconds": time.perf_counter() - started_at,
        }

    selected_name = task_names.get(decision.selected_task_id)
    return {
        "case_id": case.id,
        "run_index": run_index,
        "provider_id": provider.id,
        "expected_task_id": expected_task_id,
        "expected_task_name": case.expected_task_name,
        "selected_task_id": decision.selected_task_id,
        "selected_task_name": selected_name,
        "correct": decision.selected_task_id == expected_task_id,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "latency_seconds": time.perf_counter() - started_at,
    }


async def _warmup(client, cases, context, config: TaskChoiceBenchmarkConfig) -> int:
    errors = 0
    if config.warmup_runs < 1:
        return errors

    for _ in range(config.warmup_runs):
        try:
            await client.ChooseInitialTask(
                current_user_request=cases[0].transcript,
                session_conversations=context.session_conversations,
                session_memories=context.session_memories,
                available_tasks=context.available_tasks,
                task_choice_memories=context.task_choice_memories,
            )
        except Exception:
            errors += 1
        if config.delay_seconds > 0:
            await asyncio.sleep(config.delay_seconds)
    return errors
