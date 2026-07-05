from __future__ import annotations

from collections import deque

import numpy as np

from reframe_agent_host.voice.vad_types import (
    DetectedUtterance,
    UtteranceEvent,
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
        self._final_silence_samples = max(
            0,
            int(config.sample_rate * _remaining_final_silence_ms(config) / 1000),
        )
        self._pending = np.empty(0, dtype=np.float32)
        self._frames: list[np.ndarray] = []
        self._pending_end_samples: int | None = None
        self._pending_endpoint: DetectedUtterance | None = None
        self._recording_samples = 0
        self._recording = False

    @property
    def detector_name(self) -> str:
        return self._detector.name

    @property
    def is_recording(self) -> bool:
        return self._recording

    def accept(self, frame: np.ndarray) -> DetectedUtterance | None:
        event = self.accept_event(frame)
        if event is not None and event.kind == "endpoint":
            return event.utterance
        return None

    def accept_event(self, frame: np.ndarray) -> UtteranceEvent | None:
        mono_frame = np.asarray(frame, dtype=np.float32).reshape(-1)
        if len(mono_frame) == 0:
            return None

        self._pending = np.concatenate((self._pending, mono_frame))
        while len(self._pending) >= self._chunk_samples:
            chunk = self._pending[: self._chunk_samples]
            self._pending = self._pending[self._chunk_samples :]
            event = self._accept_chunk(chunk)
            if event is not None:
                return event

        return None

    def reset(self) -> None:
        self._pending = np.empty(0, dtype=np.float32)
        self._frames = []
        self._pending_end_samples = None
        self._pending_endpoint = None
        self._recording_samples = 0
        self._recording = False
        self._pre_roll.clear()

    def _accept_chunk(self, frame: np.ndarray) -> UtteranceEvent | None:
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

    def _accept_after_start(self, frame: np.ndarray) -> UtteranceEvent | None:
        self._frames.append(frame)
        self._recording_samples += len(frame)
        decision = self._detector.accept(frame)
        forced_end = (
            self._recording_samples / self._config.sample_rate
            >= self._config.max_utterance_seconds
        )

        if forced_end:
            return self._endpoint_event(forced_end, reset=True)

        if decision.started or decision.is_speech:
            resumed = self._pending_end_samples is not None
            self._pending_end_samples = None
            self._pending_endpoint = None
            if resumed:
                return UtteranceEvent("resumed")
            return None

        if decision.ended:
            self._pending_end_samples = 0
            return self._endpoint_event(
                forced_end,
                reset=self._final_silence_samples <= 0,
            )

        if self._pending_end_samples is None:
            return None

        self._pending_end_samples += len(frame)
        if self._pending_end_samples < self._final_silence_samples:
            return None

        endpoint = self._pending_endpoint
        self.reset()
        return UtteranceEvent("confirmed", endpoint)

    def _endpoint_event(
        self,
        forced_end: bool,
        *,
        reset: bool,
    ) -> UtteranceEvent | None:
        utterance = self._build_utterance(forced_end)
        if utterance is None:
            self.reset()
            return None

        if reset:
            self.reset()
        else:
            self._pending_endpoint = utterance
        return UtteranceEvent("endpoint", utterance)

    def _build_utterance(self, forced_end: bool) -> DetectedUtterance | None:
        samples = np.concatenate(self._frames).astype(np.float32, copy=False)
        duration_seconds = len(samples) / self._config.sample_rate

        if duration_seconds * 1000 < self._config.min_utterance_ms:
            return None

        return DetectedUtterance(
            samples=samples,
            sample_rate=self._config.sample_rate,
            duration_seconds=duration_seconds,
            forced_end=forced_end,
        )


def _remaining_final_silence_ms(config: VoiceActivityConfig) -> int:
    return max(0, config.final_silence_ms - config.min_silence_ms)
