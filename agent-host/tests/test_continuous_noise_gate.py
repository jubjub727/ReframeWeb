import asyncio
import time
import unittest

import numpy as np

import baml_sdk as types
from reframe_agent_host.keyphrases import KeyphraseSpotterConfig
from reframe_agent_host.speech.transcription import Transcript, WhisperTranscriberConfig
from reframe_agent_host.speech.triggers import TriggerPhraseConfig, TriggerPhraseMatcher
from reframe_agent_host.voice.activity import DetectedUtterance, VoiceActivityConfig
from reframe_agent_host.voice.microphone import AudioInputConfig
from reframe_agent_host.voice.turn_processor import VoiceTurnProcessor
from reframe_agent_host.voice.types import (
    CaptureResult,
    VoicePipelineConfig,
    VoiceTurnControl,
)
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


class NoopPlanner:
    async def choose_initial_task(self, _current_user_request):
        raise AssertionError("noise should not reach task choice")


class NoopConversationEvaluation:
    async def evaluate_for_memory_search(self, _current_user_request, _selected_task_id):
        raise AssertionError("noise should not reach memory search")


class NoopSearchDepth:
    async def evaluate_search_depths(
        self,
        _current_user_request,
        _selected_task_id,
        _memory_search_hints,
    ):
        raise AssertionError("noise should not reach search depth")


class NoopMemoryRetrieval:
    async def retrieve(self, _memory_search_hints, _search_depths):
        return RetrievedMemoryContext()


class NoopMemoryRelevance:
    async def evaluate_relevant_memories(
        self,
        _current_user_request,
        _selected_task_id,
        _retrieved_memories,
    ):
        raise AssertionError("noise should not reach memory relevance")


class NoopTaskPrompt:
    async def generate_task_prompt(
        self,
        _current_user_request,
        _selected_task_id,
        _selected_memories,
        selected_memory_ids=(),
    ):
        raise AssertionError("noise should not reach task prompt")


class ContinuousNoiseGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_continuous_mode_ignores_quiet_noise_before_transcription(self):
        transcriber = CountingTranscriber()
        events = []

        result = await _processor(transcriber).process(
            capture=_continuous_noise_capture(),
            conversation_mode=types.ConversationMode.CONTINUOUS_CONVERSATION,
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
                conversation_mode=types.ConversationMode.CONTINUOUS_CONVERSATION,
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
        planner=NoopPlanner(),
        conversation_evaluation=NoopConversationEvaluation(),
        search_depth=NoopSearchDepth(),
        memory_retrieval=NoopMemoryRetrieval(),
        memory_relevance=NoopMemoryRelevance(),
        task_prompt=NoopTaskPrompt(),
    )


def _voice_config():
    return VoicePipelineConfig(
        audio=AudioInputConfig(),
        voice_activity=VoiceActivityConfig(),
        keyphrases=KeyphraseSpotterConfig(),
        triggers=TriggerPhraseConfig(),
        transcription=WhisperTranscriberConfig(),
        conversation_mode=types.ConversationMode.CONTINUOUS_CONVERSATION,
        task_choice_enabled=False,
    )


def _continuous_noise_capture():
    return CaptureResult(
        conversation_mode=types.ConversationMode.CONTINUOUS_CONVERSATION,
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
