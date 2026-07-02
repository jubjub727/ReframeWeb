from __future__ import annotations

import asyncio
import time
from typing import Any

from reframe_agent_host.baml_client import b
from reframe_agent_host.benchmarks.conversation_evaluation_case_types import (
    ConversationEvaluationBenchmarkCase,
)
from reframe_agent_host.benchmarks.conversation_evaluation_config import (
    ConversationEvaluationBenchmarkConfig,
)
from reframe_agent_host.benchmarks.conversation_evaluation_context import (
    conversation_context,
    conversation_evaluation_memory_context,
    memory_context,
    selected_task_context,
)
from reframe_agent_host.benchmarks.task_choice_provider_index import model_id_for_surface
from reframe_agent_host.benchmarks.task_choice_stats import latency_summary
from reframe_memory import ProviderNode


async def benchmark_conversation_evaluation_provider(
    provider: ProviderNode,
    cases: tuple[ConversationEvaluationBenchmarkCase, ...],
    config: ConversationEvaluationBenchmarkConfig,
) -> dict[str, Any]:
    client = b.with_options(client=provider.content.baml_surface)
    warmup_errors = await _warmup(client, cases, config)
    results = []
    latencies = []
    error_count = 0

    for case in cases:
        for run_index in range(config.runs):
            result = await _run_case(client, provider, case, run_index)
            results.append(result)
            if "latency_seconds" in result:
                latencies.append(result["latency_seconds"])
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
        "errors": error_count,
        "warmup_errors": warmup_errors,
        "latency_seconds": latency_summary(latencies),
        "case_results": results,
    }


async def _run_case(
    client,
    provider: ProviderNode,
    case: ConversationEvaluationBenchmarkCase,
    run_index: int,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        hints = await client.EvaluateConversationForMemorySearch(
            current_user_request=case.current_user_request,
            session_conversations=conversation_context(case.session_conversations),
            session_memories=memory_context(case.session_memories),
            selected_task=selected_task_context(case.selected_task),
            conversation_evaluation_memories=conversation_evaluation_memory_context(
                case.conversation_evaluation_memories
            ),
        )
    except Exception as exc:
        return {
            "case_id": case.id,
            "run_index": run_index,
            "provider_id": provider.id,
            "error": str(exc),
            "latency_seconds": time.perf_counter() - started_at,
        }

    return {
        "case_id": case.id,
        "run_index": run_index,
        "provider_id": provider.id,
        "hints": hints.model_dump(mode="json"),
        "latency_seconds": time.perf_counter() - started_at,
    }


async def _warmup(
    client,
    cases: tuple[ConversationEvaluationBenchmarkCase, ...],
    config: ConversationEvaluationBenchmarkConfig,
) -> int:
    errors = 0
    if config.warmup_runs < 1 or not cases:
        return errors

    for _ in range(config.warmup_runs):
        try:
            case = cases[0]
            await client.EvaluateConversationForMemorySearch(
                current_user_request=case.current_user_request,
                session_conversations=conversation_context(case.session_conversations),
                session_memories=memory_context(case.session_memories),
                selected_task=selected_task_context(case.selected_task),
                conversation_evaluation_memories=conversation_evaluation_memory_context(
                    case.conversation_evaluation_memories
                ),
            )
        except Exception:
            errors += 1
        if config.delay_seconds > 0:
            await asyncio.sleep(config.delay_seconds)
    return errors
