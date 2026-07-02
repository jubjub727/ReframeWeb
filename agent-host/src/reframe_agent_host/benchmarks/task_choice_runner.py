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
)
from reframe_agent_host.benchmarks.task_choice_provider_run import benchmark_provider
from reframe_memory import MemoryDatabase


async def run_task_choice_benchmark(
    database: MemoryDatabase,
    config: TaskChoiceBenchmarkConfig,
) -> dict[str, Any]:
    cases = _select_cases(task_choice_lack_of_capability_cases(), config.case_ids)
    providers = await direct_model_providers(database, config.provider_ids)
    if not providers:
        raise ValueError(
            "no direct OpenCode Go model providers found in memory; "
            "run seed-opencode-go-providers first"
        )
    context = await TaskChoiceContextBuilder(
        database=database,
        session_id=config.session_id,
    ).build()
    task_names = {task.id: task.name for task in context.available_tasks}
    expected_task_ids = _expected_task_ids(cases, task_names)

    provider_results = []
    for index, provider in enumerate(providers):
        result = await benchmark_provider(
            provider,
            cases,
            expected_task_ids,
            task_names,
            context,
            config,
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
        "providers": provider_results,
        "summary": _summary(provider_results, cases, config),
    }


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
    config: TaskChoiceBenchmarkConfig,
) -> dict[str, Any]:
    total = sum(int(result["total"]) for result in provider_results)
    correct = sum(int(result["correct"]) for result in provider_results)
    errors = sum(int(result["errors"]) for result in provider_results)
    return {
        "providers": len(provider_results),
        "cases": len(cases),
        "runs_per_case": config.runs,
        "total": total,
        "correct": correct,
        "errors": errors,
        "accuracy": correct / total if total else 0.0,
        "delay_seconds": config.delay_seconds,
        "provider_cooldown_seconds": config.provider_cooldown_seconds,
    }
