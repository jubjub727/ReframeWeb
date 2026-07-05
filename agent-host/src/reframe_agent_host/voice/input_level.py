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
