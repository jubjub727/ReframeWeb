from __future__ import annotations

import asyncio
import time
from typing import Any

from baml_core import Collector

import baml_sdk as baml
from reframe_agent_host.agent_flow.baml_clients import client_kwargs
from reframe_agent_host.agent_flow.machine_state import local_machine_state_context
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
from reframe_agent_host.benchmarks.reasoning_efforts import (
    collector_stop_reason,
    collector_usage,
    opencode_reasoning_effort_candidates,
    opencode_reasoning_effort_client,
    unsupported_reasoning_effort_error,
)
from reframe_agent_host.benchmarks.task_choice_provider_index import model_id_for_surface
from reframe_agent_host.benchmarks.task_choice_stats import latency_summary
from reframe_memory import ProviderNode


async def discover_conversation_evaluation_reasoning_efforts(
    provider: ProviderNode,
    cases: tuple[ConversationEvaluationBenchmarkCase, ...],
    config: ConversationEvaluationBenchmarkConfig,
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    if config.reasoning_efforts:
        return config.reasoning_efforts, [
            _discovery_result(provider, effort, supported=True, source="configured")
            for effort in config.reasoning_efforts
        ]

    supported = []
    results = []
    for effort in opencode_reasoning_effort_candidates(
        provider,
        config.reasoning_effort_candidates,
    ):
        result = await _probe_conversation_evaluation_reasoning_effort(
            provider,
            cases,
            effort,
        )
        results.append(result)
        if result["supported"]:
            supported.append(effort)
    return tuple(supported), results


async def benchmark_conversation_evaluation_provider(
    provider: ProviderNode,
    cases: tuple[ConversationEvaluationBenchmarkCase, ...],
    config: ConversationEvaluationBenchmarkConfig,
    reasoning_effort: str,
) -> dict[str, Any]:
    client, benchmark_client = opencode_reasoning_effort_client(
        provider,
        reasoning_effort,
    )
    warmup_errors = await _warmup(client, cases, config)
    results = []
    latencies = []
    error_count = 0

    for case in cases:
        for run_index in range(config.runs):
            result = await _run_case(
                client,
                provider,
                case,
                run_index,
                reasoning_effort,
            )
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
        "base_baml_surface": provider.content.baml_surface,
        "benchmark_client": benchmark_client,
        "model_id": model_id_for_surface(provider.content.baml_surface),
        "reasoning_effort": reasoning_effort,
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
    reasoning_effort: str,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    collector = Collector(
        name=(
            f"conversation-evaluation-{provider.id}-"
            f"{reasoning_effort}-{case.id}-{run_index}"
        )
    )
    try:
        hints = await baml.ChooseMemorySearch_async(
            current_user_request=case.current_user_request,
            current_conversation=_current_conversation(
                conversation_context(case.session_conversations)
            ),
            session_memories=memory_context(case.session_memories),
            selected_task=selected_task_context(case.selected_task),
            conversation_evaluation_memories=conversation_evaluation_memory_context(
                case.conversation_evaluation_memories
            ),
            machine_state=local_machine_state_context("Benchmark machine state"),
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

    return {
        "case_id": case.id,
        "run_index": run_index,
        "provider_id": provider.id,
        "reasoning_effort": reasoning_effort,
        "hints": hints.model_dump(mode="json"),
        "latency_seconds": time.perf_counter() - started_at,
        "usage": collector_usage(collector),
        "stop_reason": collector_stop_reason(collector),
    }


async def _probe_conversation_evaluation_reasoning_effort(
    provider: ProviderNode,
    cases: tuple[ConversationEvaluationBenchmarkCase, ...],
    effort: str,
) -> dict[str, Any]:
    if not cases:
        return _discovery_result(provider, effort, supported=False, error="no cases")

    client, benchmark_client = opencode_reasoning_effort_client(
        provider,
        effort,
    )
    case = cases[0]
    collector = Collector(
        name=f"conversation-evaluation-discovery-{provider.id}-{effort}"
    )
    started_at = time.perf_counter()
    try:
        await baml.ChooseMemorySearch_async(
            current_user_request=case.current_user_request,
            current_conversation=_current_conversation(
                conversation_context(case.session_conversations)
            ),
            session_memories=memory_context(case.session_memories),
            selected_task=selected_task_context(case.selected_task),
            conversation_evaluation_memories=conversation_evaluation_memory_context(
                case.conversation_evaluation_memories
            ),
            machine_state=local_machine_state_context("Benchmark machine state"),
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
            await baml.ChooseMemorySearch_async(
                current_user_request=case.current_user_request,
                current_conversation=_current_conversation(
                    conversation_context(case.session_conversations)
                ),
                session_memories=memory_context(case.session_memories),
                selected_task=selected_task_context(case.selected_task),
                conversation_evaluation_memories=conversation_evaluation_memory_context(
                    case.conversation_evaluation_memories
                ),
                machine_state=local_machine_state_context("Benchmark machine state"),
                **client_kwargs(client),
            )
        except Exception:
            errors += 1
        if config.delay_seconds > 0:
            await asyncio.sleep(config.delay_seconds)
    return errors


def _current_conversation(conversations):
    return conversations[0] if conversations else None


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
