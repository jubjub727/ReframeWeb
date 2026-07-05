from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np


VoiceDetectorName = Literal["auto", "silero", "energy"]
UtteranceEventKind = Literal["endpoint", "resumed", "confirmed"]


@dataclass(frozen=True)
class VoiceActivityConfig:
    sample_rate: int = 16_000
    chunk_ms: int = 32
    detector: VoiceDetectorName = "auto"
    threshold: float = 0.35
    min_silence_ms: int = 0
    final_silence_ms: int = 1450
    speech_pad_ms: int = 0
    pre_speech_ms: int = 320
    min_utterance_ms: int = 250
    max_utterance_seconds: float = 20.0
    energy_start_threshold: float = 0.012
    energy_end_threshold: float = 0.008
    energy_start_ms: int = 96


@dataclass(frozen=True)
class VoiceActivityDecision:
    started: bool = False
    ended: bool = False
    is_speech: bool = False
    speech_probability: float | None = None


@dataclass(frozen=True)
class DetectedUtterance:
    samples: np.ndarray
    sample_rate: int
    duration_seconds: float
    forced_end: bool


@dataclass(frozen=True)
class UtteranceEvent:
    kind: UtteranceEventKind
    utterance: DetectedUtterance | None = None


class VoiceActivityDetector(Protocol):
    name: str

    def accept(self, frame: np.ndarray) -> VoiceActivityDecision:
        ...
