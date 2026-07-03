from __future__ import annotations

from dataclasses import dataclass

from reframe_agent_host.benchmarks.reasoning_efforts import (
    OPENCODE_GO_REASONING_EFFORT_CANDIDATES,
)


SEARCH_DEPTH_DEFAULT_MODEL_ID = "glm-5.1"


@dataclass(frozen=True)
class ControlFlowBenchmarkConfig:
    runs: int
    warmup_runs: int
    delay_seconds: float
    provider_cooldown_seconds: float
    provider_ids: tuple[str, ...] = ()
    case_ids: tuple[str, ...] = ()
    search_depth_model_id: str = SEARCH_DEPTH_DEFAULT_MODEL_ID
    reasoning_efforts: tuple[str, ...] = ()
    reasoning_effort_candidates: tuple[str, ...] = (
        OPENCODE_GO_REASONING_EFFORT_CANDIDATES
    )
