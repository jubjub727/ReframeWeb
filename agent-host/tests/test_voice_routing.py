import time
import unittest

import numpy as np

from reframe_agent_host.baml_client import types
from reframe_agent_host.keyphrases import KeyphraseDetection, KeyphraseSpotterConfig
from reframe_agent_host.speech.transcription import Transcript, WhisperTranscriberConfig
from reframe_agent_host.speech.triggers import TriggerPhraseConfig, TriggerPhraseMatcher
from reframe_agent_host.voice.activity import DetectedUtterance, VoiceActivityConfig
from reframe_agent_host.voice.microphone import AudioInputConfig
from reframe_agent_host.voice.turn_processor import VoiceTurnProcessor
from reframe_agent_host.voice.types import CaptureResult, VoicePipelineConfig


class StubTranscriber:
    def transcribe(self, _samples, _sample_rate):
        return Transcript(
            text="jarvis do this",
            language="en",
            duration_seconds=1.0,
            segments=[],
        )


class RecordingPlanner:
    def __init__(self):
        self.current_user_request = None

    async def choose_initial_task(self, current_user_request):
        self.current_user_request = current_user_request
        return types.TaskChoiceDecision(
            selected_task_id="task:needs_more_information",
            confidence=1.0,
            reason="test",
        )


class RecordingConversationEvaluation:
    def __init__(self):
        self.current_user_request = None
        self.selected_task_id = None

    async def evaluate_for_memory_search(
        self,
        current_user_request,
        selected_task_id,
    ):
        self.current_user_request = current_user_request
        self.selected_task_id = selected_task_id
        return types.ConversationMemorySearchHints(
            tags=types.MemoryTagSearch(
                any_of=["test"],
                all_of=[],
                none_of=[],
            ),
            strings=types.MemoryStringSearch(
                contains=["do this"],
                equals=[],
            ),
        )


class VoiceRoutingTests(unittest.IsolatedAsyncioTestCase):
    def test_wake_keyword_is_removed_from_routed_transcript(self):
        matcher = TriggerPhraseMatcher(TriggerPhraseConfig())

        detection = matcher.match("Jarvis, do this.")

        self.assertIsNotNone(detection)
        self.assertEqual(detection.routed_transcript, "do this")

    async def test_task_choice_receives_routed_transcript(self):
        planner = RecordingPlanner()
        conversation_evaluation = RecordingConversationEvaluation()
        processor = VoiceTurnProcessor(
            config=_voice_config(),
            transcriber=StubTranscriber(),
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            planner=planner,
            conversation_evaluation=conversation_evaluation,
        )

        result = await processor.process(
            capture=_capture_result(),
            conversation_mode=types.ConversationMode.WakeCommand,
            model_prepare_seconds=0.0,
            total_started_at=time.perf_counter(),
            on_event=None,
        )

        self.assertEqual(result.transcript.text, "jarvis do this")
        self.assertEqual(result.routed_transcript, "do this")
        self.assertEqual(planner.current_user_request, "do this")
        self.assertEqual(conversation_evaluation.current_user_request, "do this")
        self.assertEqual(
            conversation_evaluation.selected_task_id,
            "task:needs_more_information",
        )
        self.assertEqual(result.memory_search_hints.strings.contains, ["do this"])


def _voice_config():
    return VoicePipelineConfig(
        audio=AudioInputConfig(),
        voice_activity=VoiceActivityConfig(),
        keyphrases=KeyphraseSpotterConfig(),
        triggers=TriggerPhraseConfig(),
        transcription=WhisperTranscriberConfig(),
        conversation_mode=types.ConversationMode.WakeCommand,
    )


def _capture_result():
    return CaptureResult(
        conversation_mode=types.ConversationMode.WakeCommand,
        keyphrase_detection=KeyphraseDetection(
            kind="wake_command",
            phrase="jarvis",
            hypstr="jarvis",
            confirmed=True,
            phrase_end_sample=None,
        ),
        utterance=DetectedUtterance(
            samples=np.zeros(1600, dtype=np.float32),
            sample_rate=16000,
            duration_seconds=0.1,
            forced_end=False,
        ),
        mode_switched=False,
        keyphrase_wait_seconds=0.0,
        listen_seconds=0.1,
        wait_for_speech_seconds=0.0,
        speech_capture_wall_seconds=0.1,
    )


if __name__ == "__main__":
    unittest.main()
