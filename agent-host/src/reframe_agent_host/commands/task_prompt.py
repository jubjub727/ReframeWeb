from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from reframe_agent_host.benchmarks import (
    TaskPromptBenchmarkConfig,
    run_task_prompt_benchmark,
)
from reframe_memory import open_memory_database


async def run_benchmark_task_prompt(
    runs: int,
    warmup_runs: int,
    delay_seconds: float,
    provider_cooldown_seconds: float,
    provider_ids: list[str] | None,
    case_ids: list[str] | None,
    reasoning_efforts: list[str] | None,
    reasoning_effort_candidates: list[str] | None,
    refresh_snapshots: bool,
    output: str | None,
) -> int:
    database = await open_memory_database()
    try:
        await database.apply_schema()
        await database.ensure_roots()
        config_kwargs = {
            "runs": runs,
            "warmup_runs": warmup_runs,
            "delay_seconds": delay_seconds,
            "provider_cooldown_seconds": provider_cooldown_seconds,
            "provider_ids": tuple(provider_ids or ()),
            "case_ids": tuple(case_ids or ()),
            "refresh_snapshots": refresh_snapshots,
        }
        if reasoning_efforts is not None:
            config_kwargs["reasoning_efforts"] = tuple(reasoning_efforts)
        if reasoning_effort_candidates is not None:
            config_kwargs["reasoning_effort_candidates"] = tuple(
                reasoning_effort_candidates
            )
        result = await run_task_prompt_benchmark(
            database=database,
            config=TaskPromptBenchmarkConfig(**config_kwargs),
        )
        output_path = _write_benchmark_result(result, output)
        _print_benchmark_saved(output_path, result)
        return 0
    finally:
        await database.close()


def _write_benchmark_result(result: dict[str, object], output: str | None) -> Path:
    path = Path(output) if output else _default_benchmark_output_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path.resolve()


def _default_benchmark_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("benchmark-results") / f"task-prompt-{stamp}.json"


def _print_benchmark_saved(path: Path, result: dict[str, object]) -> None:
    summary = result.get("summary")
    print(f"benchmark JSON saved to {path}")
    if isinstance(summary, dict):
        print(
            "summary: "
            f"base_providers={summary.get('base_providers')} "
            f"provider_effort_runs={summary.get('provider_effort_runs')} "
            f"cases={summary.get('cases')} "
            f"snapshots={summary.get('snapshots')} "
            f"total={summary.get('total')} "
            f"correct={summary.get('correct')} "
            f"errors={summary.get('errors')} "
            f"accuracy={summary.get('accuracy')}"
        )
