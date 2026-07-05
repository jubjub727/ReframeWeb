from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AudioQualityThresholds:
    min_peak: float = 0.12
    max_peak: float = 0.95
    min_active_rms: float = 0.018
    min_active_fraction: float = 0.08
    max_clipped_fraction: float = 0.001
    frame_ms: int = 50


@dataclass(frozen=True)
class AudioQualityMetrics:
    sample_rate: int
    duration_seconds: float
    peak: float
    rms: float
    active_rms: float
    active_fraction: float
    clipped_fraction: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "sample_rate": self.sample_rate,
            "duration_seconds": self.duration_seconds,
            "peak": self.peak,
            "rms": self.rms,
            "active_rms": self.active_rms,
            "active_fraction": self.active_fraction,
            "clipped_fraction": self.clipped_fraction,
        }


@dataclass(frozen=True)
class AudioQualityReport:
    ok: bool
    metrics: AudioQualityMetrics
    problems: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "metrics": self.metrics.to_dict(),
            "problems": list(self.problems),
        }


def analyze_audio_quality(
    samples: np.ndarray,
    sample_rate: int,
    thresholds: AudioQualityThresholds = AudioQualityThresholds(),
) -> AudioQualityReport:
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    abs_audio = np.abs(audio)

    duration_seconds = len(audio) / sample_rate if sample_rate else 0.0
    peak = float(np.max(abs_audio)) if len(abs_audio) else 0.0
    rms = _rms(audio)
    active_rms, active_fraction = _active_level(audio, sample_rate, thresholds.frame_ms)
    clipped_fraction = (
        float(np.count_nonzero(abs_audio >= thresholds.max_peak) / len(abs_audio))
        if len(abs_audio)
        else 0.0
    )

    metrics = AudioQualityMetrics(
        sample_rate=sample_rate,
        duration_seconds=duration_seconds,
        peak=peak,
        rms=rms,
        active_rms=active_rms,
        active_fraction=active_fraction,
        clipped_fraction=clipped_fraction,
    )
    problems = _quality_problems(metrics, thresholds)
    return AudioQualityReport(ok=not problems, metrics=metrics, problems=problems)


def _quality_problems(
    metrics: AudioQualityMetrics,
    thresholds: AudioQualityThresholds,
) -> tuple[str, ...]:
    problems: list[str] = []
    if metrics.peak < thresholds.min_peak:
        problems.append("speech is too quiet")
    if metrics.active_rms < thresholds.min_active_rms:
        problems.append("active speech level is too low")
    if metrics.active_fraction < thresholds.min_active_fraction:
        problems.append("not enough speech was captured")
    if metrics.clipped_fraction > thresholds.max_clipped_fraction:
        problems.append("audio is clipping")
    return tuple(problems)


def _active_level(
    audio: np.ndarray,
    sample_rate: int,
    frame_ms: int,
) -> tuple[float, float]:
    if len(audio) == 0 or sample_rate <= 0:
        return 0.0, 0.0

    frame_samples = max(1, int(sample_rate * frame_ms / 1000))
    frames = [
        audio[index : index + frame_samples]
        for index in range(0, len(audio), frame_samples)
    ]
    frame_rms = np.asarray([_rms(frame) for frame in frames], dtype=np.float32)
    if len(frame_rms) == 0:
        return 0.0, 0.0

    active_frames = frame_rms >= 0.006
    active_fraction = float(np.count_nonzero(active_frames) / len(frame_rms))
    if not np.any(active_frames):
        return 0.0, active_fraction

    active_samples = np.concatenate(
        [frame for frame, active in zip(frames, active_frames) if active]
    )
    return _rms(active_samples), active_fraction


def _rms(samples: np.ndarray) -> float:
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float32))))
