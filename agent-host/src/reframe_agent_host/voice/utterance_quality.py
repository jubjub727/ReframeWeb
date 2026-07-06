from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class UtteranceQuality:
    peak: float
    active_rms: float
    active_ms: float


@dataclass(frozen=True)
class ContinuousNoiseGate:
    min_peak: float = 0.035
    min_active_rms: float = 0.012
    min_active_ms: float = 180.0
    active_frame_rms: float = 0.008
    frame_ms: int = 32


def should_ignore_continuous_utterance(
    samples: np.ndarray,
    sample_rate: int,
    gate: ContinuousNoiseGate = ContinuousNoiseGate(),
) -> tuple[bool, UtteranceQuality]:
    quality = utterance_quality(samples, sample_rate, gate)
    ignored = (
        quality.peak < gate.min_peak
        or quality.active_rms < gate.min_active_rms
        or quality.active_ms < gate.min_active_ms
    )
    return ignored, quality


def utterance_quality(
    samples: np.ndarray,
    sample_rate: int,
    gate: ContinuousNoiseGate = ContinuousNoiseGate(),
) -> UtteranceQuality:
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    if len(audio) == 0 or sample_rate <= 0:
        return UtteranceQuality(peak=0.0, active_rms=0.0, active_ms=0.0)

    peak = float(np.max(np.abs(audio)))
    frame_samples = max(1, int(sample_rate * gate.frame_ms / 1000))
    usable = len(audio) - (len(audio) % frame_samples)
    if usable <= 0:
        return UtteranceQuality(
            peak=peak,
            active_rms=_rms(audio),
            active_ms=len(audio) * 1000 / sample_rate,
        )

    frames = audio[:usable].reshape(-1, frame_samples)
    frame_rms = np.sqrt(np.mean(np.square(frames), axis=1, dtype=np.float64))
    active_frames = frames[frame_rms >= gate.active_frame_rms]
    if len(active_frames) == 0:
        return UtteranceQuality(peak=peak, active_rms=0.0, active_ms=0.0)

    active_audio = active_frames.reshape(-1)
    active_ms = len(active_audio) * 1000 / sample_rate
    return UtteranceQuality(
        peak=peak,
        active_rms=_rms(active_audio),
        active_ms=active_ms,
    )


def _rms(samples: np.ndarray) -> float:
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))
