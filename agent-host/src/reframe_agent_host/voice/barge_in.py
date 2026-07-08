from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import numpy as np

from reframe_agent_host.voice.vad_silero import SileroVoiceActivityDetector
from reframe_agent_host.voice.vad_types import (
    VoiceActivityConfig,
    VoiceActivityDecision,
    VoiceActivityDetector,
)


DetectorFactory = Callable[[VoiceActivityConfig], VoiceActivityDetector]


class TtsBargeInDetector:
    def __init__(
        self,
        config: VoiceActivityConfig,
        *,
        detector_factory: DetectorFactory | None = None,
        required_voice_ms: int = 160,
    ) -> None:
        self._config = replace(config, detector="silero")
        self._detector_factory = detector_factory or SileroVoiceActivityDetector
        self._detector: VoiceActivityDetector | None = None
        self._disabled = False
        self._required_samples = max(
            1,
            int(self._config.sample_rate * required_voice_ms / 1000),
        )
        self._voice_samples = 0
        self._triggered = False

    def accept(self, frame: np.ndarray, *, tts_active: bool) -> bool:
        if not tts_active:
            self.reset()
            return False
        if self._disabled:
            return False

        detector = self._get_detector()
        if detector is None:
            return False

        decision = detector.accept(np.asarray(frame, dtype=np.float32).reshape(-1))
        if _is_voice(decision):
            self._voice_samples += len(frame)
            if not self._triggered and self._voice_samples >= self._required_samples:
                self._triggered = True
                return True
            return False

        if decision.ended or not decision.is_speech:
            self._voice_samples = 0
            self._triggered = False
        return False

    def reset(self) -> None:
        self._voice_samples = 0
        self._triggered = False

    def _get_detector(self) -> VoiceActivityDetector | None:
        if self._detector is not None:
            return self._detector
        try:
            self._detector = self._detector_factory(self._config)
        except Exception:
            self._disabled = True
            return None
        return self._detector


def _is_voice(decision: VoiceActivityDecision) -> bool:
    return decision.started or decision.is_speech
