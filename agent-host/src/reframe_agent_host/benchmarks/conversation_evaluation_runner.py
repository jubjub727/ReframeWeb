from __future__ import annotations

import asyncio
from typing import Any

from reframe_agent_host.benchmarks.conversation_evaluation_case_types import (
    ConversationEvaluationBenchmarkCase,
)
from reframe_agent_host.benchmarks.conversation_evaluation_cases import (
    conversation_evaluation_cases,
)
from reframe_agent_host.benchmarks.conversation_evaluation_config import (
    ConversationEvaluationBenchmarkConfig,
)
from reframe_agent_host.benchmarks.conversation_evaluation_provider_run import (
    benchmark_conversation_evaluation_provider,
)
from reframe_agent_host.benchmarks.task_choice_provider_index import (
    direct_model_providers,
)
from reframe_memory import MemoryDatabase


async def run_conversation_evaluation_benchmark(
    database: MemoryDatabase,
    config: ConversationEvaluationBenchmarkConfig,
) -> dict[str, Any]:
    cases = _select_cases(conversation_evaluation_cases(), config.case_ids)
    providers = await direct_model_providers(database, config.provider_ids)
    if not providers:
        raise ValueError(
            "no direct OpenCode Go model providers found in memory; "
            "run seed-opencode-go-providers first"
        )

    provider_results = []
    for index, provider in enumerate(providers):
        result = await benchmark_conversation_evaluation_provider(
            provider,
            cases,
            config,
        )
        provider_results.append(result)
        if index < len(providers) - 1 and config.provider_cooldown_seconds > 0:
            await asyncio.sleep(config.provider_cooldown_seconds)

    return {
        "benchmark": "conversation_evaluation_memory_search",
        "cases": [_case_summary(case) for case in cases],
        "providers": provider_results,
        "summary": _summary(provider_results, cases, config),
    }


def _select_cases(
    cases: tuple[ConversationEvaluationBenchmarkCase, ...],
    case_ids: tuple[str, ...],
) -> tuple[ConversationEvaluationBenchmarkCase, ...]:
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


def _case_summary(case: ConversationEvaluationBenchmarkCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "current_user_request": case.current_user_request,
        "selected_task_name": case.selected_task.name,
        "session_conversations": len(case.session_conversations),
        "session_memories": len(case.session_memories),
        "conversation_evaluation_memories": len(
            case.conversation_evaluation_memories
        ),
        "review_focus": case.review_focus,
    }


def _summary(
    provider_results: list[dict[str, Any]],
    cases: tuple[ConversationEvaluationBenchmarkCase, ...],
    config: ConversationEvaluationBenchmarkConfig,
) -> dict[str, Any]:
    total = sum(int(result["total"]) for result in provider_results)
    errors = sum(int(result["errors"]) for result in provider_results)
    return {
        "providers": len(provider_results),
        "cases": len(cases),
        "runs_per_case": config.runs,
        "total": total,
        "errors": errors,
        "delay_seconds": config.delay_seconds,
        "provider_cooldown_seconds": config.provider_cooldown_seconds,
    }
