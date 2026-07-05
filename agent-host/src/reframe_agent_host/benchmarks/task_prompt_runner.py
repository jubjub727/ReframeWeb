from __future__ import annotations

import asyncio
from typing import Any

from reframe_agent_host.benchmarks.task_choice_provider_index import (
    direct_model_providers,
)
from reframe_agent_host.benchmarks.task_choice_stats import latency_summary
from reframe_agent_host.benchmarks.task_prompt_cases import (
    TaskPromptBenchmarkCase,
    task_prompt_cases,
)
from reframe_agent_host.benchmarks.task_prompt_config import (
    TaskPromptBenchmarkConfig,
)
from reframe_agent_host.benchmarks.task_prompt_execution import (
    build_task_prompt_snapshot,
    snapshot_payload,
)
from reframe_agent_host.benchmarks.task_prompt_provider_run import (
    benchmark_task_prompt_provider,
    discover_task_prompt_reasoning_efforts,
)
from reframe_memory import MemoryDatabase


async def run_task_prompt_benchmark(
    database: MemoryDatabase,
    config: TaskPromptBenchmarkConfig,
) -> dict[str, Any]:
    cases = _select_cases(task_prompt_cases(), config.case_ids)
    providers = await direct_model_providers(database, config.provider_ids)
    if not providers:
        raise ValueError(
            "no direct OpenCode Go model providers found; "
            "run seed-opencode-go-providers first"
        )

    snapshots = []
    for case in cases:
        snapshots.append(
            await build_task_prompt_snapshot(
                database,
                case,
                refresh=config.refresh_snapshots,
            )
        )
    snapshots = tuple(snapshots)

    provider_results = []
    discovery_results = []
    for index, provider in enumerate(providers):
        efforts, discovery = await discover_task_prompt_reasoning_efforts(
            provider,
            snapshots,
            config,
        )
        discovery_results.extend(discovery)
        for effort in efforts:
            result = await benchmark_task_prompt_provider(
                provider,
                snapshots,
                config,
                effort,
            )
            provider_results.append(result)
        if index < len(providers) - 1 and config.provider_cooldown_seconds > 0:
            await asyncio.sleep(config.provider_cooldown_seconds)

    return {
        "benchmark": "task_prompt",
        "cases": [_case_summary(case) for case in cases],
        "snapshots": [snapshot_payload(snapshot) for snapshot in snapshots],
        "reasoning_effort_discovery": discovery_results,
        "providers": provider_results,
        "summary": _summary(provider_results, snapshots, providers, config),
    }


def _select_cases(
    cases: tuple[TaskPromptBenchmarkCase, ...],
    case_ids: tuple[str, ...],
) -> tuple[TaskPromptBenchmarkCase, ...]:
    if not case_ids:
        return cases

    wanted = set(case_ids)
    selected = tuple(case for case in cases if case.id in wanted)
    if len(selected) != len(wanted):
        known = {case.id for case in cases}
        missing = sorted(wanted - known)
        msg = "unknown benchmark case ids: " + ", ".join(missing)
        raise ValueError(msg)
    return selected


def _case_summary(case: TaskPromptBenchmarkCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "current_user_request": case.current_user_request,
        "expected_task_name": case.expected_task_name,
        "conversation_name": case.conversation_name,
        "messages": len(case.messages),
        "session_memories": len(case.session_memories),
    }


def _summary(
    provider_results: list[dict[str, Any]],
    snapshots,
    providers,
    config: TaskPromptBenchmarkConfig,
) -> dict[str, Any]:
    total = sum(int(result["total"]) for result in provider_results)
    correct = sum(int(result["correct"]) for result in provider_results)
    errors = sum(int(result["errors"]) for result in provider_results)
    snapshot_errors = sum(1 for snapshot in snapshots if snapshot.error is not None)
    snapshot_correct = sum(1 for snapshot in snapshots if snapshot.task_correct)
    snapshot_latencies = [snapshot.latency_seconds for snapshot in snapshots]
    latencies = [
        case_result["latency_seconds"]
        for result in provider_results
        for case_result in result.get("case_results", [])
        if isinstance(case_result, dict) and "latency_seconds" in case_result
    ]
    return {
        "base_providers": len(providers),
        "provider_effort_runs": len(provider_results),
        "providers": len(provider_results),
        "cases": len(snapshots),
        "snapshots": len(snapshots),
        "reasoning_effort_candidates": list(config.reasoning_effort_candidates),
        "configured_reasoning_efforts": list(config.reasoning_efforts),
        "refresh_snapshots": config.refresh_snapshots,
        "snapshot_errors": snapshot_errors,
        "snapshot_task_correct": snapshot_correct,
        "snapshot_accuracy": snapshot_correct / len(snapshots) if snapshots else 0.0,
        "snapshot_latency_seconds": latency_summary(snapshot_latencies),
        "runs_per_case": config.runs,
        "total": total,
        "correct": correct,
        "errors": errors,
        "accuracy": correct / total if total else 0.0,
        "latency_seconds": latency_summary(latencies),
        "delay_seconds": config.delay_seconds,
        "provider_cooldown_seconds": config.provider_cooldown_seconds,
    }
