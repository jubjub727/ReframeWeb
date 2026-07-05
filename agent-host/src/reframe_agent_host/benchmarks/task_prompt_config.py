from __future__ import annotations

from dataclasses import dataclass

from reframe_agent_host.benchmarks.reasoning_efforts import (
    OPENCODE_GO_REASONING_EFFORT_CANDIDATES,
)


@dataclass(frozen=True)
class TaskPromptBenchmarkConfig:
    runs: int
    warmup_runs: int
    delay_seconds: float
    provider_cooldown_seconds: float
    provider_ids: tuple[str, ...] = ()
    case_ids: tuple[str, ...] = ()
    refresh_snapshots: bool = False
    reasoning_efforts: tuple[str, ...] = ()
    reasoning_effort_candidates: tuple[str, ...] = (
        OPENCODE_GO_REASONING_EFFORT_CANDIDATES
    )
