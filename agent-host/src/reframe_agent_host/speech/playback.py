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

    def clear(self) -> None:
        with self._lock:
            self._chunks.clear()
            self._queued_samples = 0

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
                if count == len(chunk):
                    self._chunks.popleft()
                else:
                    self._chunks[0] = chunk[count:]
        outdata[:] = output.reshape(-1, 1)
