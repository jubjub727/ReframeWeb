from __future__ import annotations

import json
from pathlib import Path

from reframe_agent_host.benchmarks.config import ControlFlowBenchmarkConfig
from reframe_agent_host.benchmarks.runner import run_control_flow_benchmark
from reframe_agent_host.commands.control_flow_report import print_control_flow_report
from reframe_agent_host.commands.benchmarking import (
    benchmark_config_values,
    execute_benchmark,
)


async def run_benchmark_control_flow(
    runs: int,
    warmup_runs: int,
    delay_seconds: float,
    provider_cooldown_seconds: float,
    provider_ids: list[str] | None,
    search_depth_model_id: str | None,
    case_ids: list[str] | None,
    reasoning_efforts: list[str] | None,
    reasoning_effort_candidates: list[str] | None,
    output: str | None,
) -> int:
    extra = {}
    if search_depth_model_id is not None:
        extra["search_depth_model_id"] = search_depth_model_id
    values = benchmark_config_values(
        runs=runs,
        warmup_runs=warmup_runs,
        delay_seconds=delay_seconds,
        provider_cooldown_seconds=provider_cooldown_seconds,
        provider_ids=provider_ids,
        case_ids=case_ids,
        reasoning_efforts=reasoning_efforts,
        reasoning_effort_candidates=reasoning_effort_candidates,
        **extra,
    )
    return await execute_benchmark(
        config=ControlFlowBenchmarkConfig(**values),
        runner=run_control_flow_benchmark,
        output=output,
        output_name="control-flow",
        reporter=_print_benchmark_saved,
    )


def run_analyze_control_flow_benchmark(path: str) -> int:
    result = json.loads(Path(path).read_text(encoding="utf-8"))
    _print_benchmark_loaded(Path(path).resolve(), result)
    return 0


def _print_benchmark_saved(path: Path, result: dict[str, object]) -> None:
    print(f"benchmark JSON saved to {path}")
    print_control_flow_report(result)


def _print_benchmark_loaded(path: Path, result: dict[str, object]) -> None:
    print(f"benchmark JSON loaded from {path}")
    print_control_flow_report(result)
