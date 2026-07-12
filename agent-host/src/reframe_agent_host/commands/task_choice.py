from __future__ import annotations

import json

from baml_sdk import opencode_go as baml_opencode_go

from reframe_agent_host.agent_flow.task_choice import (
    TaskChoicePlanner,
)
from reframe_agent_host.benchmarks.config import TaskChoiceBenchmarkConfig
from reframe_agent_host.benchmarks.runner import run_task_choice_benchmark
from reframe_agent_host.benchmarks.task_choice_result_analysis import (
    task_choice_failed_provider_groups,
)
from reframe_agent_host.memory_seed import (
    ensure_core_tasks,
    ensure_opencode_go_providers,
)
from reframe_agent_host.commands.benchmarking import (
    benchmark_config_values,
    execute_benchmark,
    print_benchmark_summary,
)
from reframe_agent_host.memory_readiness import require_memory_ready
from reframe_memory import open_memory_database


async def run_choose_task(
    transcript: str,
    session_id: str | None,
    conversation_id: str | None,
    client_name: str | None,
) -> int:
    database = await open_memory_database()
    try:
        await require_memory_ready(database, require_task_catalog=True)
        result = await TaskChoicePlanner(
            database=database,
            session_id=session_id,
            conversation_id=conversation_id,
            client_name=client_name,
        ).choose_initial_task(transcript)
        print(json.dumps(result.model_dump(mode="json"), indent=2))
        return 0
    finally:
        await database.close()


async def run_benchmark_task_choice(
    session_id: str | None,
    runs: int,
    warmup_runs: int,
    delay_seconds: float,
    provider_cooldown_seconds: float,
    provider_ids: list[str] | None,
    case_ids: list[str] | None,
    reasoning_efforts: list[str] | None,
    reasoning_effort_candidates: list[str] | None,
    output: str | None,
) -> int:
    values = benchmark_config_values(
        runs=runs,
        warmup_runs=warmup_runs,
        delay_seconds=delay_seconds,
        provider_cooldown_seconds=provider_cooldown_seconds,
        provider_ids=provider_ids,
        case_ids=case_ids,
        reasoning_efforts=reasoning_efforts,
        reasoning_effort_candidates=reasoning_effort_candidates,
        session_id=session_id,
    )
    return await execute_benchmark(
        config=TaskChoiceBenchmarkConfig(**values),
        runner=run_task_choice_benchmark,
        output=output,
        output_name="task-choice",
        reporter=_print_benchmark_saved,
    )


async def run_memory_setup() -> int:
    database = await open_memory_database()
    try:
        await database.apply_schema()
        await database.ensure_roots()
        print("memory schema and roots are ready")
        return 0
    finally:
        await database.close()


async def run_seed_core_tasks() -> int:
    database = await open_memory_database()
    try:
        await database.apply_schema()
        await database.ensure_roots()
        result = await ensure_core_tasks(database)
        print(
            json.dumps(
                {
                    "provider_ids": list(result.provider_ids),
                    "created_task_ids": list(result.created_task_ids),
                    "existing_task_ids": list(result.existing_task_ids),
                    "updated_task_ids": list(result.updated_task_ids),
                },
                indent=2,
            )
        )
        return 0
    finally:
        await database.close()


async def run_seed_opencode_go_providers() -> int:
    database = await open_memory_database()
    try:
        await database.apply_schema()
        await database.ensure_roots()
        result = await ensure_opencode_go_providers(database)
        print(
            json.dumps(
                {
                    "created_provider_ids": list(result.created_provider_ids),
                    "existing_provider_ids": list(result.existing_provider_ids),
                    "removed_provider_ids": list(result.removed_provider_ids),
                },
                indent=2,
            )
        )
        return 0
    finally:
        await database.close()


def run_list_opencode_go_models() -> int:
    print(
        json.dumps(
            [
                {
                    "model_id": reference.model_id,
                    "direct_baml_surface": reference.direct_baml_surface,
                    "workspace_baml_surface": reference.workspace_baml_surface,
                    "reasoning_efforts": list(reference.reasoning_efforts),
                }
                for reference in baml_opencode_go.ModelInventory()
            ],
            indent=2,
        )
    )
    return 0


def run_analyze_task_choice_benchmark(path: str) -> int:
    groups = task_choice_failed_provider_groups(path)
    if not groups:
        print("no failed benchmark runs found")
        return 0

    for group in groups:
        effort = f"/{group.reasoning_effort}" if group.reasoning_effort else ""
        print(
            f"{group.status}: {group.model_id}{effort} "
            f"{group.provider_id} {group.baml_surface} "
            f"cases={','.join(group.case_ids)}"
        )
    return 0


def _print_benchmark_saved(path, result: dict[str, object]) -> None:
    print_benchmark_summary(path, result, _SUMMARY_FIELDS)


_SUMMARY_FIELDS = (
    ("base_providers", "base_providers"),
    ("provider_effort_runs", "provider_effort_runs"),
    ("model", "task_choice_model_id"),
    ("cases", "cases"),
    ("total", "total"),
    ("correct", "correct"),
    ("errors", "errors"),
    ("accuracy", "accuracy"),
)
