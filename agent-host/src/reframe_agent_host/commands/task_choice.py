from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from reframe_agent_host.agent_flow.task_choice import (
    TaskChoicePlanner,
)
from reframe_agent_host.benchmarks import (
    TaskChoiceBenchmarkConfig,
    run_task_choice_benchmark,
)
from reframe_agent_host.benchmarks.task_choice_result_analysis import (
    task_choice_failed_provider_groups,
)
from reframe_agent_host.memory_seed import (
    ensure_core_tasks,
    ensure_opencode_go_providers,
    opencode_go_model_inventory,
)
from reframe_memory import open_memory_database


async def run_choose_task(
    transcript: str,
    session_id: str | None,
    client_name: str | None,
) -> int:
    database = await open_memory_database()
    try:
        await database.apply_schema()
        await database.ensure_roots()
        result = await TaskChoicePlanner(
            database=database,
            session_id=session_id,
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
    output: str | None,
) -> int:
    database = await open_memory_database()
    try:
        await database.apply_schema()
        await database.ensure_roots()
        result = await run_task_choice_benchmark(
            database=database,
            config=TaskChoiceBenchmarkConfig(
                session_id=session_id,
                runs=runs,
                warmup_runs=warmup_runs,
                delay_seconds=delay_seconds,
                provider_cooldown_seconds=provider_cooldown_seconds,
                provider_ids=tuple(provider_ids or ()),
                case_ids=tuple(case_ids or ()),
            ),
        )
        output_path = _write_benchmark_result(result, output)
        _print_benchmark_saved(output_path, result)
        return 0
    finally:
        await database.close()


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
                    "provider_id": result.provider_id,
                    "created_task_ids": list(result.created_task_ids),
                    "existing_task_ids": list(result.existing_task_ids),
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
                }
                for reference in opencode_go_model_inventory()
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
        print(
            f"{group.status}: {group.model_id} "
            f"{group.provider_id} {group.baml_surface} "
            f"cases={','.join(group.case_ids)}"
        )
    return 0


def _write_benchmark_result(result: dict[str, object], output: str | None) -> Path:
    path = Path(output) if output else _default_benchmark_output_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path.resolve()


def _default_benchmark_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("benchmark-results") / f"task-choice-{stamp}.json"


def _print_benchmark_saved(path: Path, result: dict[str, object]) -> None:
    summary = result.get("summary")
    print(f"benchmark JSON saved to {path}")
    if isinstance(summary, dict):
        print(
            "summary: "
            f"providers={summary.get('providers')} "
            f"cases={summary.get('cases')} "
            f"total={summary.get('total')} "
            f"correct={summary.get('correct')} "
            f"errors={summary.get('errors')} "
            f"accuracy={summary.get('accuracy')}"
        )
