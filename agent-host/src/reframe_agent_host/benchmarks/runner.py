from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from baml_sdk import benchmarks as baml_benchmarks

from reframe_agent_host.agent_flow.task_choice import TaskChoiceContextBuilder
from reframe_agent_host.benchmarks.config import (
    ControlFlowBenchmarkConfig,
    ConversationEvaluationBenchmarkConfig,
    MemoryRelevanceBenchmarkConfig,
    TaskChoiceBenchmarkConfig,
    TaskPromptBenchmarkConfig,
)
from reframe_agent_host.benchmarks.control_flow_execution import (
    build_control_flow_snapshot,
    snapshot_payload as control_flow_snapshot,
)
from reframe_agent_host.benchmarks.memory_relevance_execution import (
    build_memory_relevance_snapshot,
    snapshot_payload as memory_relevance_snapshot,
)
from reframe_agent_host.benchmarks.provider_runs import (
    benchmark_control_flow_provider,
    benchmark_conversation_evaluation_provider,
    benchmark_memory_relevance_provider,
    benchmark_task_choice_provider,
    benchmark_task_prompt_provider,
    discover_control_flow_reasoning_efforts,
    discover_conversation_evaluation_reasoning_efforts,
    discover_memory_relevance_reasoning_efforts,
    discover_task_choice_reasoning_efforts,
    discover_task_prompt_reasoning_efforts,
)
from reframe_agent_host.benchmarks.reporting import (
    benchmark_summary,
    control_flow_case_summary,
    conversation_case_summary,
    memory_relevance_case_summary,
    task_prompt_case_summary,
)
from reframe_agent_host.benchmarks.provider_catalog import (
    direct_model_providers,
    model_id_for_surface,
)
from reframe_agent_host.benchmarks.task_prompt_execution import (
    build_task_prompt_snapshot,
    snapshot_payload as task_prompt_snapshot,
)
async def run_control_flow_benchmark(database, config: ControlFlowBenchmarkConfig):
    cases = _select_cases(baml_benchmarks.ControlFlowCases(), config.case_ids)
    providers = _model_providers(
        await direct_model_providers(database, config.provider_ids),
        config.provider_ids,
        config.search_depth_model_id,
    )
    _require_providers(providers, config.search_depth_model_id)
    snapshots = tuple([await build_control_flow_snapshot(case) for case in cases])
    results, discovery = await _provider_matrix(
        providers,
        config,
        lambda provider: discover_control_flow_reasoning_efforts(
            provider, snapshots, config
        ),
        lambda provider, effort: benchmark_control_flow_provider(
            provider, snapshots, config, effort
        ),
    )
    summary = benchmark_summary(results, snapshots, providers, config)
    summary["search_depth_model_id"] = config.search_depth_model_id
    return {
        "benchmark": "control_flow_search_depth",
        "cases": [control_flow_case_summary(case) for case in cases],
        "snapshots": [control_flow_snapshot(item) for item in snapshots],
        "reasoning_effort_discovery": discovery,
        "providers": results,
        "summary": summary,
    }


async def run_memory_relevance_benchmark(
    database, config: MemoryRelevanceBenchmarkConfig
):
    cases = _select_cases(baml_benchmarks.ControlFlowCases(), config.case_ids)
    providers = await direct_model_providers(database, config.provider_ids)
    _require_providers(providers)
    snapshots = tuple(
        [await build_memory_relevance_snapshot(case) for case in cases]
    )
    results, discovery = await _provider_matrix(
        providers,
        config,
        lambda provider: discover_memory_relevance_reasoning_efforts(
            provider, snapshots, config
        ),
        lambda provider, effort: benchmark_memory_relevance_provider(
            provider, snapshots, config, effort
        ),
    )
    return {
        "benchmark": "memory_relevance",
        "cases": [memory_relevance_case_summary(case) for case in cases],
        "snapshots": [memory_relevance_snapshot(item) for item in snapshots],
        "reasoning_effort_discovery": discovery,
        "providers": results,
        "summary": benchmark_summary(
            results, snapshots, providers, config, live_latency=True
        ),
    }


async def run_task_prompt_benchmark(database, config: TaskPromptBenchmarkConfig):
    cases = _select_cases(baml_benchmarks.TaskPromptCases(), config.case_ids)
    providers = await direct_model_providers(database, config.provider_ids)
    _require_providers(providers)
    snapshots = tuple(
        [
            await build_task_prompt_snapshot(
                database, case, refresh=config.refresh_snapshots
            )
            for case in cases
        ]
    )
    results, discovery = await _provider_matrix(
        providers,
        config,
        lambda provider: discover_task_prompt_reasoning_efforts(
            provider, snapshots, config
        ),
        lambda provider, effort: benchmark_task_prompt_provider(
            provider, snapshots, config, effort
        ),
    )
    summary = benchmark_summary(
        results, snapshots, providers, config, live_latency=True
    )
    summary["refresh_snapshots"] = config.refresh_snapshots
    return {
        "benchmark": "task_prompt",
        "cases": [task_prompt_case_summary(case) for case in cases],
        "snapshots": [task_prompt_snapshot(item) for item in snapshots],
        "reasoning_effort_discovery": discovery,
        "providers": results,
        "summary": summary,
    }


async def run_conversation_evaluation_benchmark(
    database, config: ConversationEvaluationBenchmarkConfig
):
    cases = _select_cases(
        baml_benchmarks.ConversationEvaluationCases(), config.case_ids
    )
    providers = _model_providers(
        await direct_model_providers(database, config.provider_ids),
        config.provider_ids,
        config.conversation_evaluation_model_id,
    )
    _require_providers(providers, config.conversation_evaluation_model_id)
    results, discovery = await _provider_matrix(
        providers,
        config,
        lambda provider: discover_conversation_evaluation_reasoning_efforts(
            provider, cases, config
        ),
        lambda provider, effort: benchmark_conversation_evaluation_provider(
            provider, cases, config, effort
        ),
    )
    summary = benchmark_summary(results, cases, providers, config)
    summary["conversation_evaluation_model_id"] = (
        config.conversation_evaluation_model_id
    )
    return {
        "benchmark": "conversation_evaluation_memory_search",
        "cases": [conversation_case_summary(case) for case in cases],
        "reasoning_effort_discovery": discovery,
        "providers": results,
        "summary": summary,
    }


async def run_task_choice_benchmark(database, config: TaskChoiceBenchmarkConfig):
    cases = _select_cases(baml_benchmarks.TaskChoiceCases(), config.case_ids)
    providers = _model_providers(
        await direct_model_providers(database, config.provider_ids),
        config.provider_ids,
        config.task_choice_model_id,
    )
    _require_providers(providers, config.task_choice_model_id)
    context = await TaskChoiceContextBuilder(
        database=database, session_id=config.session_id
    ).build()
    task_names = {task.id: task.name for task in context.available_tasks}
    expected_ids = _expected_task_ids(cases, task_names)
    results, discovery = await _provider_matrix(
        providers,
        config,
        lambda provider: discover_task_choice_reasoning_efforts(
            provider, cases, context, config
        ),
        lambda provider, effort: benchmark_task_choice_provider(
            provider, cases, expected_ids, task_names, context, config, effort
        ),
    )
    summary = benchmark_summary(results, cases, providers, config)
    summary["task_choice_model_id"] = config.task_choice_model_id
    return {
        "benchmark": "task_choice_lack_of_capability",
        "cases": [case.model_dump(mode="json") for case in cases],
        "reasoning_effort_discovery": discovery,
        "providers": results,
        "summary": summary,
    }


async def _provider_matrix(
    providers,
    config,
    discover: Callable[[Any], Awaitable[tuple[tuple[str | None, ...], list]]],
    benchmark: Callable[[Any, str | None], Awaitable[dict]],
):
    results = []
    discovery_results = []
    for index, provider in enumerate(providers):
        efforts, discovery = await discover(provider)
        discovery_results.extend(discovery)
        for effort in efforts:
            results.append(await benchmark(provider, effort))
        if index < len(providers) - 1 and config.provider_cooldown_seconds > 0:
            await asyncio.sleep(config.provider_cooldown_seconds)
    return results, discovery_results


def _select_cases(cases, case_ids):
    cases = tuple(cases)
    if not case_ids:
        return cases
    wanted = set(case_ids)
    selected = tuple(case for case in cases if case.id in wanted)
    missing = wanted - {case.id for case in selected}
    if missing:
        raise ValueError("unknown benchmark case ids: " + ", ".join(sorted(missing)))
    return selected


def _model_providers(providers, configured_ids, model_id):
    if configured_ids:
        return providers
    return tuple(
        provider
        for provider in providers
        if model_id_for_surface(provider.content.baml_surface) == model_id
    )


def _require_providers(providers, model_id=None):
    if providers:
        return
    target = f" for {model_id}" if model_id else ""
    raise ValueError(
        f"no direct OpenCode Go model providers found{target}; "
        "run seed-opencode-go-providers first"
    )


def _expected_task_ids(cases, task_names):
    by_name = {name: task_id for task_id, name in task_names.items()}
    missing = {case.expected_task_name for case in cases} - set(by_name)
    if missing:
        raise ValueError(
            "missing expected benchmark tasks: " + ", ".join(sorted(missing))
        )
    return {case.expected_task_name: by_name[case.expected_task_name] for case in cases}


def _search_depth_providers(providers, config):
    return _model_providers(
        providers, config.provider_ids, config.search_depth_model_id
    )


def _conversation_evaluation_providers(providers, config):
    return _model_providers(
        providers,
        config.provider_ids,
        config.conversation_evaluation_model_id,
    )


def _task_choice_providers(providers, config):
    return _model_providers(providers, config.provider_ids, config.task_choice_model_id)
