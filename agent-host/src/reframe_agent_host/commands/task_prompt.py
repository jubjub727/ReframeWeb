from __future__ import annotations

from pathlib import Path

from reframe_agent_host.benchmarks.config import TaskPromptBenchmarkConfig
from reframe_agent_host.benchmarks.runner import run_task_prompt_benchmark
from reframe_agent_host.commands.benchmarking import (
    benchmark_config_values,
    execute_benchmark,
    print_benchmark_summary,
)


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
    values = benchmark_config_values(
        runs=runs,
        warmup_runs=warmup_runs,
        delay_seconds=delay_seconds,
        provider_cooldown_seconds=provider_cooldown_seconds,
        provider_ids=provider_ids,
        case_ids=case_ids,
        reasoning_efforts=reasoning_efforts,
        reasoning_effort_candidates=reasoning_effort_candidates,
        refresh_snapshots=refresh_snapshots,
    )
    return await execute_benchmark(
        config=TaskPromptBenchmarkConfig(**values),
        runner=run_task_prompt_benchmark,
        output=output,
        output_name="task-prompt",
        reporter=_print_benchmark_saved,
    )


def _print_benchmark_saved(path: Path, result: dict[str, object]) -> None:
    print_benchmark_summary(path, result, _SUMMARY_FIELDS)


_SUMMARY_FIELDS = (
    ("base_providers", "base_providers"),
    ("provider_effort_runs", "provider_effort_runs"),
    ("cases", "cases"),
    ("snapshots", "snapshots"),
    ("total", "total"),
    ("correct", "correct"),
    ("errors", "errors"),
    ("accuracy", "accuracy"),
)
