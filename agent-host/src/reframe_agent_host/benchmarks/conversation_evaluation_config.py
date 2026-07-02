from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationEvaluationBenchmarkConfig:
    runs: int
    warmup_runs: int
    delay_seconds: float
    provider_cooldown_seconds: float
    provider_ids: tuple[str, ...] = ()
    case_ids: tuple[str, ...] = ()
