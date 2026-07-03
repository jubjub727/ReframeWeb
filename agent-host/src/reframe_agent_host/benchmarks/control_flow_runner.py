from __future__ import annotations

import asyncio
from typing import Any

from reframe_agent_host.benchmarks.control_flow_case_types import (
    ControlFlowBenchmarkCase,
)
from reframe_agent_host.benchmarks.control_flow_cases import control_flow_cases
from reframe_agent_host.benchmarks.control_flow_config import (
    ControlFlowBenchmarkConfig,
)
from reframe_agent_host.benchmarks.control_flow_execution import (
    build_control_flow_snapshot,
    snapshot_payload,
)
from reframe_agent_host.benchmarks.control_flow_provider_run import (
    benchmark_control_flow_provider,
    discover_control_flow_reasoning_efforts,
)
from reframe_agent_host.benchmarks.task_choice_provider_index import (
    direct_model_providers,
    model_id_for_surface,
)
from reframe_agent_host.benchmarks.task_choice_stats import latency_summary
from reframe_memory import MemoryDatabase


async def run_control_flow_benchmark(
    database: MemoryDatabase,
    config: ControlFlowBenchmarkConfig,
) -> dict[str, Any]:
    cases = _select_cases(control_flow_cases(), config.case_ids)
    providers = await direct_model_providers(database, config.provider_ids)
    providers = _search_depth_providers(providers, config)
    if not providers:
        raise ValueError(
            f"no direct OpenCode Go model providers found for "
            f"{config.search_depth_model_id}; "
            "run seed-opencode-go-providers first"
        )
    snapshots = []
    for case in cases:
        snapshots.append(await build_control_flow_snapshot(case))
    snapshots = tuple(snapshots)

    provider_results = []
    discovery_results = []
    for index, provider in enumerate(providers):
        efforts, discovery = await discover_control_flow_reasoning_efforts(
            provider,
            snapshots,
            config,
        )
        discovery_results.extend(discovery)
        for effort in efforts:
            result = await benchmark_control_flow_provider(
                provider,
                snapshots,
                config,
                effort,
            )
            provider_results.append(result)
        if index < len(providers) - 1 and config.provider_cooldown_seconds > 0:
            await asyncio.sleep(config.provider_cooldown_seconds)

    return {
        "benchmark": "control_flow_search_depth",
        "cases": [_case_summary(case) for case in cases],
        "snapshots": [snapshot_payload(snapshot) for snapshot in snapshots],
        "reasoning_effort_discovery": discovery_results,
        "providers": provider_results,
        "summary": _summary(provider_results, snapshots, providers, config),
    }


def _search_depth_providers(
    providers,
    config: ControlFlowBenchmarkConfig,
):
    if config.provider_ids:
        return providers
    return tuple(
        provider
        for provider in providers
        if model_id_for_surface(provider.content.baml_surface)
        == config.search_depth_model_id
    )


def _select_cases(
    cases: tuple[ControlFlowBenchmarkCase, ...],
    case_ids: tuple[str, ...],
) -> tuple[ControlFlowBenchmarkCase, ...]:
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


def _case_summary(case: ControlFlowBenchmarkCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "current_timestamp": case.current_timestamp,
        "current_user_request": case.current_user_request,
        "expected_task_id": case.expected_task_id,
        "available_tasks": len(case.available_tasks),
        "session": {
            "id": case.session.id,
            "name": case.session.name,
            "created_at": case.session.created_at,
            "updated_at": case.session.updated_at,
            "read_at": case.session.read_at,
            "conversations": len(case.session.conversations),
            "memories": len(case.session.memories),
        },
        "task_choice_memories": len(case.task_choice_memories),
        "conversation_evaluation_memories": len(
            case.conversation_evaluation_memories
        ),
        "search_depth_memories": len(case.search_depth_memories),
    }


def _summary(
    provider_results: list[dict[str, Any]],
    snapshots,
    providers,
    config: ControlFlowBenchmarkConfig,
) -> dict[str, Any]:
    total = sum(int(result["total"]) for result in provider_results)
    correct = sum(int(result["correct"]) for result in provider_results)
    errors = sum(int(result["errors"]) for result in provider_results)
    snapshot_latencies = [snapshot.latency_seconds for snapshot in snapshots]
    snapshot_errors = sum(1 for snapshot in snapshots if snapshot.error is not None)
    snapshot_correct = sum(1 for snapshot in snapshots if snapshot.task_correct)
    return {
        "base_providers": len(providers),
        "provider_effort_runs": len(provider_results),
        "providers": len(provider_results),
        "cases": len(snapshots),
        "snapshots": len(snapshots),
        "search_depth_model_id": config.search_depth_model_id,
        "reasoning_effort_candidates": list(config.reasoning_effort_candidates),
        "configured_reasoning_efforts": list(config.reasoning_efforts),
        "snapshot_errors": snapshot_errors,
        "snapshot_task_correct": snapshot_correct,
        "snapshot_accuracy": snapshot_correct / len(snapshots) if snapshots else 0.0,
        "snapshot_latency_seconds": latency_summary(snapshot_latencies),
        "runs_per_case": config.runs,
        "total": total,
        "correct": correct,
        "errors": errors,
        "accuracy": correct / total if total else 0.0,
        "delay_seconds": config.delay_seconds,
        "provider_cooldown_seconds": config.provider_cooldown_seconds,
    }
