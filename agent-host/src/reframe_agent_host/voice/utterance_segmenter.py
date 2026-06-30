from __future__ import annotations

from collections import deque

import numpy as np

from reframe_agent_host.voice.vad_types import (
    DetectedUtterance,
    VoiceActivityConfig,
    VoiceActivityDetector,
)


class UtteranceSegmenter:
    def __init__(self, detector: VoiceActivityDetector, config: VoiceActivityConfig) -> None:
        self._detector = detector
        self._config = config
        self._pre_roll: deque[np.ndarray] = deque(
            maxlen=max(1, round(config.pre_speech_ms / config.chunk_ms))
        )
        self._chunk_samples = max(1, int(config.sample_rate * config.chunk_ms / 1000))
        self._pending = np.empty(0, dtype=np.float32)
        self._frames: list[np.ndarray] = []
        self._recording_samples = 0
        self._recording = False

    @property
    def detector_name(self) -> str:
        return self._detector.name

    @property
    def is_recording(self) -> bool:
        return self._recording

    def accept(self, frame: np.ndarray) -> DetectedUtterance | None:
        mono_frame = np.asarray(frame, dtype=np.float32).reshape(-1)
        if len(mono_frame) == 0:
            return None

        self._pending = np.concatenate((self._pending, mono_frame))
        while len(self._pending) >= self._chunk_samples:
            chunk = self._pending[: self._chunk_samples]
            self._pending = self._pending[self._chunk_samples :]
            utterance = self._accept_chunk(chunk)
            if utterance is not None:
                return utterance

        return None

    def reset(self) -> None:
        self._pending = np.empty(0, dtype=np.float32)
        self._frames = []
        self._recording_samples = 0
        self._recording = False
        self._pre_roll.clear()

    def _accept_chunk(self, frame: np.ndarray) -> DetectedUtterance | None:
        if not self._recording:
            return self._accept_before_start(frame)

        return self._accept_after_start(frame)

    def _accept_before_start(self, frame: np.ndarray) -> None:
        self._pre_roll.append(frame)
        decision = self._detector.accept(frame)
        if decision.started:
            self._recording = True
            self._frames = list(self._pre_roll)
            self._recording_samples = sum(len(frame) for frame in self._frames)
        return None

    def _accept_after_start(self, frame: np.ndarray) -> DetectedUtterance | None:
        self._frames.append(frame)
        self._recording_samples += len(frame)
        decision = self._detector.accept(frame)
        forced_end = (
            self._recording_samples / self._config.sample_rate
            >= self._config.max_utterance_seconds
        )

        if not decision.ended and not forced_end:
            return None

        return self._finish_utterance(forced_end)

    def _finish_utterance(self, forced_end: bool) -> DetectedUtterance | None:
        samples = np.concatenate(self._frames).astype(np.float32, copy=False)
        duration_seconds = len(samples) / self._config.sample_rate
        self.reset()

        if duration_seconds * 1000 < self._config.min_utterance_ms:
            return None

        return DetectedUtterance(
            samples=samples,
            sample_rate=self._config.sample_rate,
            duration_seconds=duration_seconds,
            forced_end=forced_end,
        )
