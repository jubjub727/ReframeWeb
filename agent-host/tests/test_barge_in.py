import unittest

import numpy as np

from reframe_agent_host.voice.barge_in import TtsBargeInDetector
from reframe_agent_host.voice.vad_types import (
    VoiceActivityConfig,
    VoiceActivityDecision,
)


class FakeSileroDetector:
    name = "silero"

    def __init__(self, decisions):
        self._decisions = list(decisions)

    def accept(self, _frame):
        if self._decisions:
            return self._decisions.pop(0)
        return VoiceActivityDecision(is_speech=True)


class TtsBargeInDetectorTests(unittest.TestCase):
    def test_requires_active_tts_and_confirmed_speech_run(self):
        detector = TtsBargeInDetector(
            VoiceActivityConfig(),
            detector_factory=lambda _config: FakeSileroDetector(
                [
                    VoiceActivityDecision(started=True, is_speech=True),
                    VoiceActivityDecision(is_speech=True),
                    VoiceActivityDecision(is_speech=True),
                    VoiceActivityDecision(is_speech=True),
                    VoiceActivityDecision(is_speech=True),
                    VoiceActivityDecision(is_speech=True),
                    VoiceActivityDecision(is_speech=True),
                ]
            ),
            required_voice_ms=160,
        )
        frame = _speech_like_frame()

        self.assertFalse(detector.accept(frame, tts_active=False))
        self.assertFalse(detector.accept(frame, tts_active=True))
        self.assertFalse(detector.accept(frame, tts_active=True))
        self.assertFalse(detector.accept(frame, tts_active=True))
        self.assertFalse(detector.accept(frame, tts_active=True))
        self.assertFalse(detector.accept(frame, tts_active=True))
        self.assertTrue(detector.accept(frame, tts_active=True))
        self.assertFalse(detector.accept(frame, tts_active=True))

        self.assertFalse(detector.accept(frame, tts_active=False))

    def test_rejects_random_noise_even_when_vad_reports_speech(self):
        detector = TtsBargeInDetector(
            VoiceActivityConfig(),
            detector_factory=lambda _config: FakeSileroDetector(
                [VoiceActivityDecision(started=True, is_speech=True)]
            ),
            required_voice_ms=64,
        )
        rng = np.random.default_rng(7)
        frames = [
            rng.normal(0.0, 0.04, 512).astype(np.float32)
            for _ in range(10)
        ]

        self.assertFalse(any(detector.accept(frame, tts_active=True) for frame in frames))

    def test_rejects_audio_matching_recent_tts_reference(self):
        detector = TtsBargeInDetector(
            VoiceActivityConfig(),
            detector_factory=lambda _config: FakeSileroDetector(
                [VoiceActivityDecision(started=True, is_speech=True)]
            ),
            required_voice_ms=64,
        )
        frame = _speech_like_frame()
        reference = np.concatenate([np.zeros(512, dtype=np.float32), frame, frame])

        self.assertFalse(
            detector.accept(
                frame,
                tts_active=True,
                reference_audio=reference,
                reference_sample_rate=16_000,
            )
        )
        self.assertFalse(
            detector.accept(
                frame,
                tts_active=True,
                reference_audio=reference,
                reference_sample_rate=16_000,
            )
        )

    def test_disables_cleanly_when_silero_cannot_load(self):
        detector = TtsBargeInDetector(
            VoiceActivityConfig(),
            detector_factory=lambda _config: (_ for _ in ()).throw(RuntimeError("nope")),
        )

        self.assertFalse(
            detector.accept(np.zeros(512, dtype=np.float32), tts_active=True)
        )


def _speech_like_frame() -> np.ndarray:
    sample_rate = 16_000
    t = np.arange(512, dtype=np.float32) / sample_rate
    return (
        0.045 * np.sin(2 * np.pi * 180 * t)
        + 0.018 * np.sin(2 * np.pi * 620 * t)
    ).astype(np.float32)


if __name__ == "__main__":
    unittest.main()
