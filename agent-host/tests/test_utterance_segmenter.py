import unittest

import numpy as np

from reframe_agent_host.voice.utterance_segmenter import UtteranceSegmenter
from reframe_agent_host.voice.vad_types import (
    VoiceActivityConfig,
    VoiceActivityDecision,
)


class ScriptedDetector:
    name = "scripted"

    def __init__(self, decisions):
        self._decisions = list(decisions)

    def accept(self, _frame):
        if not self._decisions:
            return VoiceActivityDecision()
        return self._decisions.pop(0)


class UtteranceSegmenterTests(unittest.TestCase):
    def test_resumed_speech_cancels_pending_endpoint_event(self):
        segmenter = UtteranceSegmenter(
            ScriptedDetector(
                [
                    VoiceActivityDecision(started=True, is_speech=True),
                    VoiceActivityDecision(is_speech=True),
                    VoiceActivityDecision(ended=True),
                    VoiceActivityDecision(),
                    VoiceActivityDecision(started=True, is_speech=True),
                    VoiceActivityDecision(is_speech=True),
                    VoiceActivityDecision(ended=True),
                    VoiceActivityDecision(),
                    VoiceActivityDecision(),
                    VoiceActivityDecision(),
                ]
            ),
            _config(final_silence_ms=300),
        )

        self.assertIsNone(segmenter.accept_event(_frame()))
        self.assertIsNone(segmenter.accept_event(_frame()))

        first_endpoint = segmenter.accept_event(_frame())
        self.assertIsNotNone(first_endpoint)
        self.assertEqual(first_endpoint.kind, "endpoint")
        self.assertEqual(first_endpoint.utterance.duration_seconds, 0.3)

        self.assertIsNone(segmenter.accept_event(_frame()))
        resumed = segmenter.accept_event(_frame())
        self.assertIsNotNone(resumed)
        self.assertEqual(resumed.kind, "resumed")

        self.assertIsNone(segmenter.accept_event(_frame()))
        second_endpoint = segmenter.accept_event(_frame())
        self.assertIsNotNone(second_endpoint)
        self.assertEqual(second_endpoint.kind, "endpoint")
        self.assertEqual(second_endpoint.utterance.duration_seconds, 0.7)

        self.assertIsNone(segmenter.accept_event(_frame()))
        self.assertIsNone(segmenter.accept_event(_frame()))
        confirmed = segmenter.accept_event(_frame())

        self.assertIsNotNone(confirmed)
        self.assertEqual(confirmed.kind, "confirmed")

    def test_accept_returns_endpoint_immediately(self):
        segmenter = UtteranceSegmenter(
            ScriptedDetector(
                [
                    VoiceActivityDecision(started=True, is_speech=True),
                    VoiceActivityDecision(ended=True),
                ]
            ),
            _config(min_silence_ms=300, final_silence_ms=300),
        )

        self.assertIsNone(segmenter.accept(_frame()))
        result = segmenter.accept(_frame())

        self.assertIsNotNone(result)
        self.assertEqual(result.duration_seconds, 0.2)


def _config(
    *,
    min_silence_ms: int = 0,
    final_silence_ms: int = 1450,
) -> VoiceActivityConfig:
    return VoiceActivityConfig(
        sample_rate=1000,
        chunk_ms=100,
        min_silence_ms=min_silence_ms,
        final_silence_ms=final_silence_ms,
        pre_speech_ms=0,
        min_utterance_ms=0,
    )


def _frame():
    return np.ones(100, dtype=np.float32)


if __name__ == "__main__":
    unittest.main()
