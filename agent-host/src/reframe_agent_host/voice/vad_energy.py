from __future__ import annotations

import numpy as np

from reframe_agent_host.voice.vad_types import (
    VoiceActivityConfig,
    VoiceActivityDecision,
)


class EnergyVoiceActivityDetector:
    name = "energy"

    def __init__(self, config: VoiceActivityConfig) -> None:
        self._config = config
        self._in_speech = False
        self._speech_chunks = 0
        self._silence_chunks = 0
        self._start_chunks = max(1, round(config.energy_start_ms / config.chunk_ms))
        self._end_chunks = max(1, round(config.min_silence_ms / config.chunk_ms))

    def accept(self, frame: np.ndarray) -> VoiceActivityDecision:
        rms = float(np.sqrt(np.mean(np.square(frame), dtype=np.float64)))

        if not self._in_speech:
            return self._accept_before_start(rms)

        return self._accept_after_start(rms)

    def _accept_before_start(self, rms: float) -> VoiceActivityDecision:
        if rms >= self._config.energy_start_threshold:
            self._speech_chunks += 1
        else:
            self._speech_chunks = 0

        if self._speech_chunks < self._start_chunks:
            return VoiceActivityDecision(is_speech=False, speech_probability=rms)

        self._in_speech = True
        self._silence_chunks = 0
        return VoiceActivityDecision(
            started=True,
            is_speech=True,
            speech_probability=rms,
        )

    def _accept_after_start(self, rms: float) -> VoiceActivityDecision:
        if rms <= self._config.energy_end_threshold:
            self._silence_chunks += 1
        else:
            self._silence_chunks = 0

        if self._silence_chunks < self._end_chunks:
            return VoiceActivityDecision(is_speech=True, speech_probability=rms)

        self._in_speech = False
        self._speech_chunks = 0
        self._silence_chunks = 0
        return VoiceActivityDecision(
            ended=True,
            is_speech=False,
            speech_probability=rms,
        )
