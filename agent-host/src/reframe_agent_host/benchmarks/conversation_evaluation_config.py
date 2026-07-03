from __future__ import annotations

from dataclasses import dataclass

from reframe_agent_host.benchmarks.reasoning_efforts import (
    OPENCODE_GO_REASONING_EFFORT_CANDIDATES,
)


CONVERSATION_EVALUATION_DEFAULT_MODEL_ID = "glm-5.1"
CONVERSATION_EVALUATION_DEFAULT_REASONING_EFFORT = "none"


@dataclass(frozen=True)
class ConversationEvaluationBenchmarkConfig:
    runs: int
    warmup_runs: int
    delay_seconds: float
    provider_cooldown_seconds: float
    provider_ids: tuple[str, ...] = ()
    case_ids: tuple[str, ...] = ()
    conversation_evaluation_model_id: str = CONVERSATION_EVALUATION_DEFAULT_MODEL_ID
    reasoning_efforts: tuple[str, ...] = (
        CONVERSATION_EVALUATION_DEFAULT_REASONING_EFFORT,
    )
    reasoning_effort_candidates: tuple[str, ...] = (
        OPENCODE_GO_REASONING_EFFORT_CANDIDATES
    )
