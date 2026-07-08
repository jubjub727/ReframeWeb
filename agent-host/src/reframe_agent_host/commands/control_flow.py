from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from reframe_agent_host.benchmarks import (
    ControlFlowBenchmarkConfig,
    run_control_flow_benchmark,
)
from reframe_agent_host.commands.control_flow_report import print_control_flow_report
from reframe_agent_host.memory_readiness import require_memory_ready
from reframe_memory import open_memory_database


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
    database = await open_memory_database()
    try:
        await require_memory_ready(database, require_task_catalog=True)
        config_kwargs = {
            "runs": runs,
            "warmup_runs": warmup_runs,
            "delay_seconds": delay_seconds,
            "provider_cooldown_seconds": provider_cooldown_seconds,
            "provider_ids": tuple(provider_ids or ()),
            "case_ids": tuple(case_ids or ()),
            "reasoning_efforts": tuple(reasoning_efforts or ()),
        }
        if search_depth_model_id is not None:
            config_kwargs["search_depth_model_id"] = search_depth_model_id
        if reasoning_effort_candidates is not None:
            config_kwargs["reasoning_effort_candidates"] = tuple(
                reasoning_effort_candidates
            )
        result = await run_control_flow_benchmark(
            database=database,
            config=ControlFlowBenchmarkConfig(**config_kwargs),
        )
        output_path = _write_benchmark_result(result, output)
        _print_benchmark_saved(output_path, result)
        return 0
    finally:
        await database.close()


def run_analyze_control_flow_benchmark(path: str) -> int:
    result = json.loads(Path(path).read_text(encoding="utf-8"))
    _print_benchmark_loaded(Path(path).resolve(), result)
    return 0


def _write_benchmark_result(result: dict[str, object], output: str | None) -> Path:
    path = Path(output) if output else _default_benchmark_output_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path.resolve()


def _default_benchmark_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("benchmark-results") / f"control-flow-{stamp}.json"


def _print_benchmark_saved(path: Path, result: dict[str, object]) -> None:
    print(f"benchmark JSON saved to {path}")
    print_control_flow_report(result)


def _print_benchmark_loaded(path: Path, result: dict[str, object]) -> None:
    print(f"benchmark JSON loaded from {path}")
    print_control_flow_report(result)
