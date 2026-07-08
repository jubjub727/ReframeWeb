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
                ]
            ),
            required_voice_ms=160,
        )
        frame = np.zeros(512, dtype=np.float32)

        self.assertFalse(detector.accept(frame, tts_active=False))
        self.assertFalse(detector.accept(frame, tts_active=True))
        self.assertFalse(detector.accept(frame, tts_active=True))
        self.assertFalse(detector.accept(frame, tts_active=True))
        self.assertFalse(detector.accept(frame, tts_active=True))
        self.assertTrue(detector.accept(frame, tts_active=True))
        self.assertFalse(detector.accept(frame, tts_active=True))

        self.assertFalse(detector.accept(frame, tts_active=False))

    def test_disables_cleanly_when_silero_cannot_load(self):
        detector = TtsBargeInDetector(
            VoiceActivityConfig(),
            detector_factory=lambda _config: (_ for _ in ()).throw(RuntimeError("nope")),
        )

        self.assertFalse(
            detector.accept(np.zeros(512, dtype=np.float32), tts_active=True)
        )


if __name__ == "__main__":
    unittest.main()
