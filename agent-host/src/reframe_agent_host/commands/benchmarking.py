from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from reframe_agent_host.memory_readiness import require_memory_ready
from reframe_memory import MemoryDatabase, open_memory_database


BenchmarkRunner = Callable[[MemoryDatabase, Any], Awaitable[dict[str, Any]]]
BenchmarkReporter = Callable[[Path, dict[str, Any]], None]


def benchmark_config_values(
    *,
    runs: int,
    warmup_runs: int,
    delay_seconds: float,
    provider_cooldown_seconds: float,
    provider_ids: list[str] | None,
    case_ids: list[str] | None,
    reasoning_efforts: list[str] | None,
    reasoning_effort_candidates: list[str] | None,
    **extra: Any,
) -> dict[str, Any]:
    values = {
        "runs": runs,
        "warmup_runs": warmup_runs,
        "delay_seconds": delay_seconds,
        "provider_cooldown_seconds": provider_cooldown_seconds,
        "provider_ids": tuple(provider_ids or ()),
        "case_ids": tuple(case_ids or ()),
        **extra,
    }
    if reasoning_efforts is not None:
        values["reasoning_efforts"] = tuple(reasoning_efforts)
    elif reasoning_effort_candidates is not None:
        values["reasoning_efforts"] = ()
    if reasoning_effort_candidates is not None:
        values["reasoning_effort_candidates"] = tuple(
            reasoning_effort_candidates
        )
    return values


async def execute_benchmark(
    *,
    config: Any,
    runner: BenchmarkRunner,
    output: str | None,
    output_name: str,
    reporter: BenchmarkReporter,
) -> int:
    database = await open_memory_database()
    try:
        await require_memory_ready(database, require_task_catalog=True)
        result = await runner(database=database, config=config)
        path = write_benchmark_result(result, output, output_name)
        reporter(path, result)
        return 0
    finally:
        await database.close()


def write_benchmark_result(
    result: dict[str, Any],
    output: str | None,
    output_name: str,
) -> Path:
    path = Path(output) if output else _default_output_path(output_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path.resolve()


def print_benchmark_summary(
    path: Path,
    result: dict[str, Any],
    fields: Sequence[tuple[str, str]],
) -> None:
    print(f"benchmark JSON saved to {path}")
    summary = result.get("summary")
    if not isinstance(summary, dict):
        return
    values = " ".join(f"{label}={summary.get(key)}" for label, key in fields)
    print(f"summary: {values}")


def _default_output_path(output_name: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("benchmark-results") / f"{output_name}-{stamp}.json"
