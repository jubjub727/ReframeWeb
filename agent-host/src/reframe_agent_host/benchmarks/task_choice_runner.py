from __future__ import annotations

import asyncio
from typing import Any

from reframe_agent_host.agent_flow.task_choice import TaskChoiceContextBuilder
from reframe_agent_host.benchmarks.task_choice_cases import (
    TaskChoiceBenchmarkCase,
    task_choice_lack_of_capability_cases,
)
from reframe_agent_host.benchmarks.task_choice_config import TaskChoiceBenchmarkConfig
from reframe_agent_host.benchmarks.task_choice_provider_index import (
    direct_model_providers,
    model_id_for_surface,
)
from reframe_agent_host.benchmarks.task_choice_provider_run import (
    benchmark_provider,
    discover_task_choice_reasoning_efforts,
)
from reframe_memory import MemoryDatabase


async def run_task_choice_benchmark(
    database: MemoryDatabase,
    config: TaskChoiceBenchmarkConfig,
) -> dict[str, Any]:
    cases = _select_cases(task_choice_lack_of_capability_cases(), config.case_ids)
    providers = await direct_model_providers(database, config.provider_ids)
    providers = _task_choice_providers(providers, config)
    if not providers:
        raise ValueError(
            f"no direct OpenCode Go model providers found for "
            f"{config.task_choice_model_id}; "
            "run seed-opencode-go-providers first"
        )
    context = await TaskChoiceContextBuilder(
        database=database,
        session_id=config.session_id,
    ).build()
    task_names = {task.id: task.name for task in context.available_tasks}
    expected_task_ids = _expected_task_ids(cases, task_names)

    provider_results = []
    discovery_results = []
    for index, provider in enumerate(providers):
        efforts, discovery = await discover_task_choice_reasoning_efforts(
            provider,
            cases,
            context,
            config,
        )
        discovery_results.extend(discovery)
        for effort in efforts:
            result = await benchmark_provider(
                provider,
                cases,
                expected_task_ids,
                task_names,
                context,
                config,
                effort,
            )
            provider_results.append(result)
        if index < len(providers) - 1 and config.provider_cooldown_seconds > 0:
            await asyncio.sleep(config.provider_cooldown_seconds)

    return {
        "benchmark": "task_choice_lack_of_capability",
        "cases": [
            {
                "id": case.id,
                "transcript": case.transcript,
                "expected_task_name": case.expected_task_name,
            }
            for case in cases
        ],
        "reasoning_effort_discovery": discovery_results,
        "providers": provider_results,
        "summary": _summary(provider_results, cases, providers, config),
    }


def _task_choice_providers(
    providers,
    config: TaskChoiceBenchmarkConfig,
):
    if config.provider_ids:
        return providers
    return tuple(
        provider
        for provider in providers
        if model_id_for_surface(provider.content.baml_surface)
        == config.task_choice_model_id
    )


def _select_cases(
    cases: tuple[TaskChoiceBenchmarkCase, ...],
    case_ids: tuple[str, ...],
) -> tuple[TaskChoiceBenchmarkCase, ...]:
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


def _expected_task_ids(
    cases: tuple[TaskChoiceBenchmarkCase, ...],
    task_names: dict[str, str],
) -> dict[str, str]:
    by_name = {name: task_id for task_id, name in task_names.items()}
    missing = {
        case.expected_task_name
        for case in cases
        if case.expected_task_name not in by_name
    }
    if missing:
        msg = "missing expected benchmark tasks: " + ", ".join(sorted(missing))
        raise ValueError(msg)

    return {
        case.expected_task_name: by_name[case.expected_task_name]
        for case in cases
    }


def _summary(
    provider_results: list[dict[str, Any]],
    cases: tuple[TaskChoiceBenchmarkCase, ...],
    providers,
    config: TaskChoiceBenchmarkConfig,
) -> dict[str, Any]:
    total = sum(int(result["total"]) for result in provider_results)
    correct = sum(int(result["correct"]) for result in provider_results)
    errors = sum(int(result["errors"]) for result in provider_results)
    return {
        "base_providers": len(providers),
        "provider_effort_runs": len(provider_results),
        "providers": len(provider_results),
        "cases": len(cases),
        "task_choice_model_id": config.task_choice_model_id,
        "reasoning_effort_candidates": list(config.reasoning_effort_candidates),
        "configured_reasoning_efforts": list(config.reasoning_efforts),
        "runs_per_case": config.runs,
        "total": total,
        "correct": correct,
        "errors": errors,
        "accuracy": correct / total if total else 0.0,
        "delay_seconds": config.delay_seconds,
        "provider_cooldown_seconds": config.provider_cooldown_seconds,
    }
