from __future__ import annotations

from dataclasses import dataclass


OPENCODE_GO_REASONING_EFFORT_CANDIDATES = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)
SEARCH_DEPTH_DEFAULT_MODEL_ID = "glm-5.1"
CONVERSATION_EVALUATION_DEFAULT_MODEL_ID = "glm-5.1"
CONVERSATION_EVALUATION_DEFAULT_REASONING_EFFORT = "none"
TASK_CHOICE_DEFAULT_MODEL_ID = "kimi-k2.5"
TASK_CHOICE_DEFAULT_REASONING_EFFORT = "high"


@dataclass(frozen=True)
class BenchmarkConfig:
    runs: int
    warmup_runs: int
    delay_seconds: float
    provider_cooldown_seconds: float
    provider_ids: tuple[str, ...] = ()
    case_ids: tuple[str, ...] = ()
    reasoning_efforts: tuple[str, ...] = ()
    reasoning_effort_candidates: tuple[str, ...] = (
        OPENCODE_GO_REASONING_EFFORT_CANDIDATES
    )


@dataclass(frozen=True)
class ControlFlowBenchmarkConfig(BenchmarkConfig):
    search_depth_model_id: str = SEARCH_DEPTH_DEFAULT_MODEL_ID


@dataclass(frozen=True)
class ConversationEvaluationBenchmarkConfig(BenchmarkConfig):
    conversation_evaluation_model_id: str = (
        CONVERSATION_EVALUATION_DEFAULT_MODEL_ID
    )
    reasoning_efforts: tuple[str, ...] = (
        CONVERSATION_EVALUATION_DEFAULT_REASONING_EFFORT,
    )


@dataclass(frozen=True)
class MemoryRelevanceBenchmarkConfig(BenchmarkConfig):
    pass


@dataclass(frozen=True)
class TaskChoiceBenchmarkConfig(BenchmarkConfig):
    session_id: str | None = None
    task_choice_model_id: str = TASK_CHOICE_DEFAULT_MODEL_ID
    reasoning_efforts: tuple[str, ...] = (TASK_CHOICE_DEFAULT_REASONING_EFFORT,)


@dataclass(frozen=True)
class TaskPromptBenchmarkConfig(BenchmarkConfig):
    refresh_snapshots: bool = False
