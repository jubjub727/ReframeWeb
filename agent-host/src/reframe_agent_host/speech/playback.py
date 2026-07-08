from __future__ import annotations

from collections import deque
from threading import Lock
import time

import numpy as np


class QueuedAudioOutput:
    def __init__(self, sample_rate: int) -> None:
        self._sample_rate = sample_rate
        self._stream = None
        self._chunks: deque[np.ndarray] = deque()
        self._lock = Lock()
        self._queued_samples = 0
        self._played_samples = 0
        self._recent_samples = np.empty(0, dtype=np.float32)
        self._recent_sample_limit = max(1, sample_rate * 2)

    def start(self, sounddevice) -> None:
        if self._stream is not None:
            return
        stream = sounddevice.OutputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            latency="low",
            callback=self._callback,
        )
        stream.start()
        self._stream = stream

    @property
    def played_samples(self) -> int:
        with self._lock:
            return self._played_samples

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def recent_samples(self, seconds: float = 1.0) -> np.ndarray:
        sample_count = max(1, int(self._sample_rate * seconds))
        with self._lock:
            return self._recent_samples[-sample_count:].copy()

    def clear(self, *, reset_played_samples: bool = False) -> None:
        with self._lock:
            self._chunks.clear()
            self._queued_samples = 0
            if reset_played_samples:
                self._played_samples = 0
                self._recent_samples = np.empty(0, dtype=np.float32)

    def enqueue(self, samples) -> int:
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        if len(audio) == 0:
            return 0
        with self._lock:
            self._chunks.append(audio)
            self._queued_samples += len(audio)
        return len(audio)

    def wait_until_drained(self) -> None:
        while True:
            with self._lock:
                remaining = self._queued_samples
            if remaining <= 0:
                time.sleep(0.05)
                return
            time.sleep(0.01)

    def _callback(self, outdata, frames, _time_info, _status) -> None:
        output = np.zeros(frames, dtype=np.float32)
        offset = 0
        with self._lock:
            while offset < frames and self._chunks:
                chunk = self._chunks[0]
                count = min(frames - offset, len(chunk))
                output[offset : offset + count] = chunk[:count]
                offset += count
                self._queued_samples -= count
                self._played_samples += count
                if count == len(chunk):
                    self._chunks.popleft()
                else:
                    self._chunks[0] = chunk[count:]
            self._append_recent_locked(output)
        outdata[:] = output.reshape(-1, 1)

    def _append_recent_locked(self, samples: np.ndarray) -> None:
        self._recent_samples = np.concatenate((self._recent_samples, samples))
        if len(self._recent_samples) > self._recent_sample_limit:
            self._recent_samples = self._recent_samples[-self._recent_sample_limit :]
