from __future__ import annotations

import warnings

import numpy as np

from reframe_agent_host.voice.input_level import apply_input_level

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    import audioop


class AudioFrameProcessor:
    def __init__(
        self,
        source_rate: int,
        target_rate: int,
        chunk_samples: int,
        gain: float,
        limiter_ceiling: float = 0.95,
    ) -> None:
        self._source_rate = source_rate
        self._target_rate = target_rate
        self._chunk_samples = chunk_samples
        self._gain = gain
        self._limiter_ceiling = limiter_ceiling
        self._ratecv_state = None
        self._pending = np.empty(0, dtype=np.float32)

    def accept(self, samples: np.ndarray) -> list[np.ndarray]:
        resampled = self._resample(np.asarray(samples, dtype=np.float32).reshape(-1))
        processed = apply_input_level(
            resampled,
            gain=self._gain,
            limiter_ceiling=self._limiter_ceiling,
        )
        self._pending = np.concatenate((self._pending, processed))
        return self._pop_chunks()

    def _resample(self, samples: np.ndarray) -> np.ndarray:
        if self._source_rate == self._target_rate:
            return samples.copy()

        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
        converted, self._ratecv_state = audioop.ratecv(
            pcm.tobytes(),
            2,
            1,
            self._source_rate,
            self._target_rate,
            self._ratecv_state,
        )
        return np.frombuffer(converted, dtype=np.int16).astype(np.float32) / 32767.0

    def _pop_chunks(self) -> list[np.ndarray]:
        chunks: list[np.ndarray] = []
        while len(self._pending) >= self._chunk_samples:
            chunks.append(self._pending[: self._chunk_samples].copy())
            self._pending = self._pending[self._chunk_samples :]
        return chunks
