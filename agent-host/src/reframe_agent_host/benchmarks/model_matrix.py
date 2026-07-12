from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from baml_core import Collector

from reframe_agent_host.benchmarks.config import BenchmarkConfig
from reframe_agent_host.benchmarks.reasoning_efforts import (
    collector_stop_reason,
    collector_usage,
    latency_summary,
    opencode_reasoning_effort_candidates,
    opencode_reasoning_effort_client,
    unsupported_reasoning_effort_error,
)
from reframe_agent_host.benchmarks.provider_catalog import (
    model_id_for_surface,
)
from reframe_memory import ProviderNode


RunCase = Callable[[Any, ProviderNode, Any, int, str], Awaitable[dict[str, Any]]]
Warmup = Callable[[Any], Awaitable[int]]
Probe = Callable[[Any], Awaitable[Any]]


async def discover_efforts(
    provider: ProviderNode,
    config: BenchmarkConfig,
    name: str,
    probe: Probe | None,
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    if config.reasoning_efforts:
        return config.reasoning_efforts, [
            _discovery_result(provider, effort, supported=True, source="configured")
            for effort in config.reasoning_efforts
        ]
    if probe is None:
        return (), [
            _discovery_result(
                provider,
                effort,
                supported=False,
                error="no usable benchmark cases",
            )
            for effort in config.reasoning_effort_candidates
        ]

    supported = []
    results = []
    for effort in opencode_reasoning_effort_candidates(
        provider, config.reasoning_effort_candidates
    ):
        client, benchmark_client = opencode_reasoning_effort_client(provider, effort)
        collector = Collector(name=f"{name}-discovery-{provider.id}-{effort}")
        started_at = time.perf_counter()
        try:
            await probe(client)
        except Exception as error:
            is_supported = not unsupported_reasoning_effort_error(error)
            result = _discovery_result(
                provider,
                effort,
                supported=is_supported,
                benchmark_client=benchmark_client,
                error=str(error),
                latency_seconds=time.perf_counter() - started_at,
                usage=collector_usage(collector),
                stop_reason=collector_stop_reason(collector),
            )
        else:
            is_supported = True
            result = _discovery_result(
                provider,
                effort,
                supported=True,
                benchmark_client=benchmark_client,
                latency_seconds=time.perf_counter() - started_at,
                usage=collector_usage(collector),
                stop_reason=collector_stop_reason(collector),
            )
        results.append(result)
        if is_supported:
            supported.append(effort)
    return tuple(supported), results


async def benchmark_provider(
    provider: ProviderNode,
    items: Sequence[Any],
    config: BenchmarkConfig,
    effort: str,
    run_case: RunCase,
    warmup_run: Warmup,
    *,
    correct_key: str = "correct",
    include_correct: bool = True,
) -> dict[str, Any]:
    client, benchmark_client = opencode_reasoning_effort_client(provider, effort)
    warmup_errors = await warmup_run(client)
    results = []
    latencies = []
    stage_latencies: dict[str, list[float]] = {}
    for item in items:
        for run_index in range(config.runs):
            result = await run_case(client, provider, item, run_index, effort)
            results.append(result)
            latency = result.get("latency_seconds")
            if isinstance(latency, int | float):
                latencies.append(float(latency))
            for stage, value in (result.get("stage_latency_seconds") or {}).items():
                if isinstance(value, int | float):
                    stage_latencies.setdefault(stage, []).append(float(value))
            if config.delay_seconds > 0:
                await asyncio.sleep(config.delay_seconds)

    total = len(items) * config.runs
    summary = {
        "provider_id": provider.id,
        "provider_name": provider.content.name,
        "baml_surface": provider.content.baml_surface,
        "base_baml_surface": provider.content.baml_surface,
        "benchmark_client": benchmark_client,
        "model_id": model_id_for_surface(provider.content.baml_surface),
        "reasoning_effort": effort,
        "total": total,
        "errors": sum(1 for item in results if "error" in item),
        "warmup_errors": warmup_errors,
        "latency_seconds": latency_summary(latencies),
        "case_results": results,
    }
    if stage_latencies:
        summary["stage_latency_seconds"] = {
            stage: latency_summary(values)
            for stage, values in stage_latencies.items()
        }
    if include_correct:
        correct = sum(1 for item in results if item.get(correct_key) is True)
        summary["correct"] = correct
        summary["accuracy"] = correct / total if total else 0.0
    return summary


async def warmup(config: BenchmarkConfig, invoke: Callable[[], Awaitable[Any]]) -> int:
    errors = 0
    for _ in range(config.warmup_runs):
        try:
            await invoke()
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
    optional = {
        "benchmark_client": benchmark_client,
        "error": error,
        "latency_seconds": latency_seconds,
        "usage": usage,
        "stop_reason": stop_reason,
    }
    result.update({key: value for key, value in optional.items() if value is not None})
    return result
