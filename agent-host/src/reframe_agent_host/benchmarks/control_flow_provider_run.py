from __future__ import annotations

import asyncio
import time
from typing import Any

from baml_core import Collector

from reframe_agent_host.benchmarks.control_flow_config import (
    ControlFlowBenchmarkConfig,
)
from reframe_agent_host.benchmarks.control_flow_execution import (
    ControlFlowSnapshot,
    run_search_depth_case,
    search_depths,
    warmup_search_depth,
)
from reframe_agent_host.benchmarks.reasoning_efforts import (
    collector_stop_reason,
    collector_usage,
    opencode_reasoning_effort_client,
    unsupported_reasoning_effort_error,
)
from reframe_agent_host.benchmarks.task_choice_provider_index import model_id_for_surface
from reframe_agent_host.benchmarks.task_choice_stats import latency_summary
from reframe_memory import ProviderNode


async def discover_control_flow_reasoning_efforts(
    provider: ProviderNode,
    snapshots: tuple[ControlFlowSnapshot, ...],
    config: ControlFlowBenchmarkConfig,
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    if config.reasoning_efforts:
        return config.reasoning_efforts, [
            _discovery_result(provider, effort, supported=True, source="configured")
            for effort in config.reasoning_efforts
        ]

    supported = []
    results = []
    for effort in config.reasoning_effort_candidates:
        result = await _probe_control_flow_reasoning_effort(
            provider,
            snapshots,
            effort,
        )
        results.append(result)
        if result["supported"]:
            supported.append(effort)
    return tuple(supported), results


async def benchmark_control_flow_provider(
    provider: ProviderNode,
    snapshots: tuple[ControlFlowSnapshot, ...],
    config: ControlFlowBenchmarkConfig,
    reasoning_effort: str,
) -> dict[str, Any]:
    client, benchmark_client = opencode_reasoning_effort_client(
        provider,
        reasoning_effort,
    )
    warmup_errors = await warmup_search_depth(client, snapshots, config)
    results = []
    total_latencies = []
    stage_latencies = {"search_depth": []}
    correct_count = 0
    error_count = 0

    for snapshot in snapshots:
        for run_index in range(config.runs):
            result = await run_search_depth_case(
                client,
                provider,
                snapshot,
                run_index,
                reasoning_effort,
            )
            results.append(result)
            _collect_latencies(result, total_latencies, stage_latencies)
            if result.get("task_correct") is True:
                correct_count += 1
            if "error" in result:
                error_count += 1
            if config.delay_seconds > 0:
                await asyncio.sleep(config.delay_seconds)

    total = len(snapshots) * config.runs
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
        "latency_seconds": latency_summary(total_latencies),
        "stage_latency_seconds": {
            name: latency_summary(values)
            for name, values in stage_latencies.items()
        },
        "case_results": results,
    }


async def _probe_control_flow_reasoning_effort(
    provider: ProviderNode,
    snapshots: tuple[ControlFlowSnapshot, ...],
    effort: str,
) -> dict[str, Any]:
    usable = [snapshot for snapshot in snapshots if snapshot.error is None]
    if not usable:
        return _discovery_result(
            provider,
            effort,
            supported=False,
            error="no usable snapshots",
        )

    client, benchmark_client = opencode_reasoning_effort_client(
        provider,
        effort,
    )
    collector = Collector(name=f"search-depth-discovery-{provider.id}-{effort}")
    started_at = time.perf_counter()
    try:
        await search_depths(client, usable[0])
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


def _collect_latencies(result, total_latencies, stage_latencies) -> None:
    if "latency_seconds" in result:
        total_latencies.append(result["latency_seconds"])
    stages = result.get("stage_latency_seconds")
    if not isinstance(stages, dict):
        return
    for name, values in stage_latencies.items():
        if name in stages:
            values.append(stages[name])


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
