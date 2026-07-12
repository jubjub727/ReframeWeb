import asyncio
import time
import unittest

import numpy as np

from baml_sdk import context as baml_context
from reframe_agent_host.keyphrases import KeyphraseSpotterConfig
from reframe_agent_host.speech.transcription import Transcript, WhisperTranscriberConfig
from reframe_agent_host.speech.triggers import TriggerPhraseConfig, TriggerPhraseMatcher
from reframe_agent_host.voice.activity import DetectedUtterance, VoiceActivityConfig
from reframe_agent_host.voice.microphone import AudioInputConfig
from reframe_agent_host.voice.turn_processor import VoiceTurnProcessor
from reframe_agent_host.voice.capture_types import CaptureResult, VoiceTurnControl
from reframe_agent_host.voice.pipeline_config import VoicePipelineConfig
from reframe_memory import RetrievedMemoryContext


class CountingTranscriber:
    def __init__(self):
        self.calls = 0

    def transcribe(self, _samples, _sample_rate):
        self.calls += 1
        return Transcript(
            text="Tell me everything.",
            language="en",
            duration_seconds=1.0,
            segments=[],
        )


class NoopMemoryRetrieval:
    async def retrieve(self, _memory_search_hints, _search_depths):
        return RetrievedMemoryContext()


class ContinuousNoiseGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_continuous_mode_ignores_quiet_noise_before_transcription(self):
        transcriber = CountingTranscriber()
        events = []

        result = await _processor(transcriber).process(
            capture=_continuous_noise_capture(),
            conversation_mode=baml_context.ConversationMode.CONTINUOUS_CONVERSATION,
            model_prepare_seconds=0.0,
            total_started_at=time.perf_counter(),
            on_event=lambda stage, message: events.append((stage, message)),
        )

        self.assertTrue(result.ignored)
        self.assertEqual(transcriber.calls, 0)
        self.assertIn("turn-ignored", [stage for stage, _message in events])

    async def test_speculative_ignored_turn_waits_for_commit(self):
        transcriber = CountingTranscriber()
        events = []
        control = VoiceTurnControl()
        task = asyncio.create_task(
            _processor(transcriber).process(
                capture=_continuous_noise_capture(),
                conversation_mode=baml_context.ConversationMode.CONTINUOUS_CONVERSATION,
                model_prepare_seconds=0.0,
                total_started_at=time.perf_counter(),
                on_event=lambda stage, message: events.append((stage, message)),
                turn_control=control,
            )
        )

        await asyncio.sleep(0.05)
        self.assertFalse(task.done())
        self.assertNotIn("turn-ignored", [stage for stage, _message in events])

        control.commit()
        result = await task

        self.assertTrue(result.ignored)
        self.assertEqual(transcriber.calls, 0)


def _processor(transcriber):
    return VoiceTurnProcessor(
        config=_voice_config(),
        transcriber=transcriber,
        trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
        memory_retrieval=NoopMemoryRetrieval(),
    )


def _voice_config():
    return VoicePipelineConfig(
        audio=AudioInputConfig(),
        voice_activity=VoiceActivityConfig(),
        keyphrases=KeyphraseSpotterConfig(),
        triggers=TriggerPhraseConfig(),
        transcription=WhisperTranscriberConfig(),
        conversation_mode=baml_context.ConversationMode.CONTINUOUS_CONVERSATION,
        task_choice_enabled=False,
    )


def _continuous_noise_capture():
    return CaptureResult(
        conversation_mode=baml_context.ConversationMode.CONTINUOUS_CONVERSATION,
        keyphrase_detection=None,
        utterance=DetectedUtterance(
            samples=np.full(1600, 0.003, dtype=np.float32),
            sample_rate=16000,
            duration_seconds=0.1,
            forced_end=False,
        ),
        mode_switched=False,
        keyphrase_wait_seconds=None,
        listen_seconds=0.1,
        wait_for_speech_seconds=0.0,
        speech_capture_wall_seconds=0.1,
    )


if __name__ == "__main__":
    unittest.main()
