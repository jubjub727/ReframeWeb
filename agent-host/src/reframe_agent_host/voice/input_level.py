from __future__ import annotations

import numpy as np


def apply_input_level(
    samples: np.ndarray,
    *,
    gain: float,
    limiter_ceiling: float,
) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    gained = audio * max(0.0, gain)
    return limit_peaks(gained, limiter_ceiling)


def limit_peaks(samples: np.ndarray, ceiling: float) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    ceiling = max(0.0, min(1.0, ceiling))
    if ceiling <= 0 or len(audio) == 0:
        return np.zeros_like(audio)

    peak = float(np.max(np.abs(audio)))
    if peak <= ceiling:
        return audio
    return audio * (ceiling / peak)


def normalize_active_level(
    samples: np.ndarray,
    *,
    sample_rate: int,
    target_active_rms: float,
    max_gain: float,
    limiter_ceiling: float,
) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    if len(audio) == 0:
        return audio

    active_rms = _active_rms(audio, sample_rate)
    if active_rms <= 0:
        return limit_peaks(audio, limiter_ceiling)

    target = max(0.0, target_active_rms)
    gain = target / active_rms if target > 0 else 1.0
    gain = max(0.0, min(max_gain, gain))
    return apply_input_level(
        audio,
        gain=gain,
        limiter_ceiling=limiter_ceiling,
    )


def _active_rms(samples: np.ndarray, sample_rate: int) -> float:
    frame_samples = max(1, int(sample_rate * 0.02))
    usable = len(samples) - (len(samples) % frame_samples)
    if usable <= 0:
        return _rms(samples)

    frames = samples[:usable].reshape(-1, frame_samples)
    frame_rms = np.sqrt(np.mean(np.square(frames), axis=1, dtype=np.float64))
    if len(frame_rms) == 0:
        return _rms(samples)

    active_threshold = max(0.006, float(np.percentile(frame_rms, 20)) * 2.5)
    active_frames = frames[frame_rms >= active_threshold]
    if len(active_frames) == 0:
        return _rms(samples)
    return _rms(active_frames.reshape(-1))


def _rms(samples: np.ndarray) -> float:
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))
