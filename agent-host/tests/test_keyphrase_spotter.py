import unittest
from collections import deque

import numpy as np

import baml_sdk as types
from reframe_agent_host.commands.parser import build_parser
from reframe_agent_host.commands.record_wake_audio import DEFAULT_CASES
from reframe_agent_host.keyphrases import KeyphraseSpotterConfig
from reframe_agent_host.keyphrases import KeyphraseDetection
from reframe_agent_host.keyphrases.pocketsphinx_helpers import phrase_sample_span
from reframe_agent_host.keyphrases.pocketsphinx_phrase import (
    PocketSphinxPhraseSpotter,
    trim_frames_from_sample,
)
from reframe_agent_host.speech.transcription import WhisperTranscriberConfig
from reframe_agent_host.speech.triggers import TriggerPhraseConfig
from reframe_agent_host.voice.activity import VoiceActivityConfig
from reframe_agent_host.voice.capture_state import CaptureState
from reframe_agent_host.voice.keyphrase_gate import VoiceKeyphraseGate
from reframe_agent_host.voice.microphone import AudioInputConfig
from reframe_agent_host.voice.types import VoicePipelineConfig


class FakeSegment:
    def __init__(self, word, start_frame, end_frame):
        self.word = word
        self.start_frame = start_frame
        self.end_frame = end_frame


class FakeHypothesis:
    def __init__(self, hypstr):
        self.hypstr = hypstr


class FakeDecoder:
    def __init__(self, hypstr):
        self._hypothesis = FakeHypothesis(hypstr)

    def hyp(self):
        return self._hypothesis

    def seg(self):
        return ()

    def end_utt(self):
        return None


class FakeReplaySpotter:
    def __init__(self, detection):
        self.detection = detection
        self.replay_pre_ms = None
        self.closed = False

    def append(self, _frame):
        return None

    def detect(self):
        return self.detection

    def replay_frames_for_detection(self, _detection, pre_roll_ms):
        self.replay_pre_ms = pre_roll_ms
        return [np.array([float(pre_roll_ms)], dtype=np.float32)]

    def close(self):
        self.closed = True


class KeyphraseSpotterTests(unittest.TestCase):
    def test_wake_candidate_requires_keyword_confirmation(self):
        spotter = _spotter_with_decoder("jarvis")
        spotter._keyword_spotted = lambda _phrase: None

        self.assertIsNone(spotter.detect())

        spotter._frames_since_check = 1
        spotter._keyword_spotted = lambda _phrase: (0, 512)
        detection = spotter.detect()

        self.assertIsNotNone(detection)
        self.assertEqual(detection.kind, "wake_command")
        self.assertEqual(detection.phrase, "jarvis")
        self.assertEqual(detection.phrase_start_sample, 0)
        self.assertEqual(detection.phrase_end_sample, 512)

    def test_conversation_on_candidate_still_uses_phrase_match(self):
        spotter = _spotter_with_decoder("conversation on")
        spotter._keyword_spotted = lambda _phrase: None

        detection = spotter.detect()

        self.assertIsNotNone(detection)
        self.assertEqual(detection.kind, "conversation_on")
        self.assertEqual(detection.phrase, "conversation on")

    def test_parser_accepts_record_wake_audio(self):
        parser = build_parser()

        args = parser.parse_args(
            [
                "record-wake-audio",
                "--device",
                "1",
                "--case",
                "negative:hello hello",
                "--seconds",
                "1.5",
            ]
        )

        self.assertEqual(args.command, "record-wake-audio")
        self.assertEqual(args.device, "1")
        self.assertEqual(args.case, ["negative:hello hello"])
        self.assertEqual(args.seconds, 1.5)

    def test_record_wake_audio_defaults_include_trailing_wake_cases(self):
        self.assertIn("trailing-wake:do this jarvis", DEFAULT_CASES)
        self.assertIn(
            "prefixed-wake:this is a test jarvis do this",
            DEFAULT_CASES,
        )

    def test_parser_uses_stricter_wake_threshold_default(self):
        parser = build_parser()

        debug_args = parser.parse_args(["debug-wake-audio", "clip.wav"])
        voice_args = parser.parse_args(["voice-turn"])

        self.assertEqual(debug_args.wake_threshold, 1e-30)
        self.assertEqual(voice_args.wake_threshold, 1e-30)
        self.assertEqual(voice_args.wake_replay_pre_ms, 80)

    def test_phrase_sample_span_uses_first_and_last_phrase_words(self):
        segments = (
            FakeSegment("<sil>", 0, 5),
            FakeSegment("do", 6, 12),
            FakeSegment("jarvis", 13, 25),
            FakeSegment("this", 26, 31),
        )

        self.assertEqual(phrase_sample_span(segments, "jarvis"), (2080, 4160))

    def test_replay_frames_are_trimmed_to_wake_boundary(self):
        frames = [
            np.arange(0, 5, dtype=np.float32),
            np.arange(5, 10, dtype=np.float32),
            np.arange(10, 15, dtype=np.float32),
        ]

        trimmed = trim_frames_from_sample(frames, 7)

        self.assertEqual(
            [frame.tolist() for frame in trimmed],
            [[7.0, 8.0, 9.0], [10.0, 11.0, 12.0, 13.0, 14.0]],
        )

    def test_spotter_replay_starts_near_wake_phrase_end(self):
        spotter = _spotter_with_decoder("jarvis")
        spotter._frames = [
            np.arange(0, 1600, dtype=np.float32),
            np.arange(1600, 3200, dtype=np.float32),
        ]
        detection = KeyphraseDetection(
            kind="wake_command",
            phrase="jarvis",
            hypstr="jarvis",
            confirmed=True,
            phrase_start_sample=2000,
            phrase_end_sample=2600,
        )

        frames = spotter.replay_frames_for_detection(detection, pre_roll_ms=50)

        self.assertEqual(float(frames[0][0]), 1800.0)

    def test_conversation_on_replays_no_buffered_audio(self):
        detection = KeyphraseDetection(
            kind="conversation_on",
            phrase="conversation on",
            hypstr="conversation on",
            confirmed=True,
            phrase_start_sample=0,
            phrase_end_sample=1600,
        )
        spotter = FakeReplaySpotter(detection)
        state = _capture_state(spotter)
        gate = VoiceKeyphraseGate(_voice_config())

        result = gate.accept(
            np.zeros(512, dtype=np.float32),
            state,
            listen_started_at=0.0,
            emit=lambda _stage, _message: None,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.conversation_enabled)
        self.assertIsNone(spotter.replay_pre_ms)
        self.assertEqual(result.replay_frames, [])

    def test_conversation_on_without_phrase_boundary_replays_nothing(self):
        detection = KeyphraseDetection(
            kind="conversation_on",
            phrase="conversation on",
            hypstr="conversation on",
            confirmed=True,
            phrase_start_sample=None,
            phrase_end_sample=None,
        )
        spotter = FakeReplaySpotter(detection)
        state = _capture_state(spotter)
        gate = VoiceKeyphraseGate(_voice_config())

        result = gate.accept(
            np.zeros(512, dtype=np.float32),
            state,
            listen_started_at=0.0,
            emit=lambda _stage, _message: None,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.conversation_enabled)
        self.assertIsNone(spotter.replay_pre_ms)
        self.assertEqual(result.replay_frames, [])


def _spotter_with_decoder(hypstr):
    spotter = PocketSphinxPhraseSpotter(
        {
            "jarvis": "wake_command",
            "conversation on": "conversation_on",
        },
        check_interval_frames=1,
    )
    spotter._decoder.end_utt()
    spotter._decoder = FakeDecoder(hypstr)
    spotter._frames = [np.zeros(512, dtype=np.float32)]
    spotter._frames_since_check = 1
    return spotter


def _capture_state(spotter):
    state = CaptureState(
        conversation_mode=types.ConversationMode.WAKE_COMMAND,
        keyphrase_required=True,
        keyphrase_carry_frames=deque(maxlen=4),
    )
    state.keyphrase_spotter = spotter
    return state


def _voice_config():
    return VoicePipelineConfig(
        audio=AudioInputConfig(),
        voice_activity=VoiceActivityConfig(),
        keyphrases=KeyphraseSpotterConfig(replay_pre_ms=80),
        triggers=TriggerPhraseConfig(),
        transcription=WhisperTranscriberConfig(),
        conversation_mode=types.ConversationMode.WAKE_COMMAND,
    )


if __name__ == "__main__":
    unittest.main()
