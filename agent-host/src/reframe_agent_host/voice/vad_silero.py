from __future__ import annotations

import numpy as np

from reframe_agent_host.voice.vad_types import (
    VoiceActivityConfig,
    VoiceActivityDecision,
)


class SileroVoiceActivityDetector:
    name = "silero"

    def __init__(self, config: VoiceActivityConfig) -> None:
        if config.sample_rate not in (8_000, 16_000):
            raise ValueError("Silero VAD supports 8000 Hz and 16000 Hz audio.")

        from silero_vad import VADIterator, load_silero_vad
        import torch

        self._torch = torch
        try:
            model = load_silero_vad(onnx=True)
        except TypeError:
            model = load_silero_vad()

        kwargs = {
            "sampling_rate": config.sample_rate,
            "threshold": config.threshold,
            "min_silence_duration_ms": config.min_silence_ms,
            "speech_pad_ms": config.speech_pad_ms,
        }
        try:
            self._iterator = VADIterator(model, **kwargs)
        except TypeError:
            self._iterator = VADIterator(model, sampling_rate=config.sample_rate)

        self._in_speech = False

    def accept(self, frame: np.ndarray) -> VoiceActivityDecision:
        tensor = self._torch.from_numpy(np.asarray(frame, dtype=np.float32))
        event = self._iterator(tensor)

        started = isinstance(event, dict) and "start" in event
        ended = isinstance(event, dict) and "end" in event

        if started:
            self._in_speech = True
        if ended:
            self._in_speech = False

        return VoiceActivityDecision(
            started=started,
            ended=ended,
            is_speech=self._in_speech,
        )
