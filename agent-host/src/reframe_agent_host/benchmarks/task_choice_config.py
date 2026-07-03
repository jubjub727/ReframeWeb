from __future__ import annotations

from dataclasses import dataclass

from reframe_agent_host.benchmarks.reasoning_efforts import (
    OPENCODE_GO_REASONING_EFFORT_CANDIDATES,
)


TASK_CHOICE_DEFAULT_MODEL_ID = "kimi-k2.5"
TASK_CHOICE_DEFAULT_REASONING_EFFORT = "high"


@dataclass(frozen=True)
class TaskChoiceBenchmarkConfig:
    session_id: str | None
    runs: int
    warmup_runs: int
    delay_seconds: float
    provider_cooldown_seconds: float
    provider_ids: tuple[str, ...] = ()
    case_ids: tuple[str, ...] = ()
    task_choice_model_id: str = TASK_CHOICE_DEFAULT_MODEL_ID
    reasoning_efforts: tuple[str, ...] = (TASK_CHOICE_DEFAULT_REASONING_EFFORT,)
    reasoning_effort_candidates: tuple[str, ...] = (
        OPENCODE_GO_REASONING_EFFORT_CANDIDATES
    )
