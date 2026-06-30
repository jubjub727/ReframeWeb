from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def read_mono_wav(path: str | Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())

    if sample_width != 2:
        raise ValueError(f"{path} must be 16-bit PCM WAV.")

    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, sample_rate


def chunk_samples(
    samples: np.ndarray,
    sample_rate: int,
    chunk_ms: int,
):
    chunk_size = max(1, int(sample_rate * chunk_ms / 1000))
    for index in range(0, len(samples), chunk_size):
        yield samples[index : index + chunk_size]
