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
from reframe_memory import RetrievedMemoryContext


class StubTranscriber:
    def __init__(self, text="jarvis do this"):
        self.text = text

    def transcribe(self, _samples, _sample_rate):
        return Transcript(
            text=self.text,
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


class RecordingSearchDepth:
    def __init__(self):
        self.current_user_request = None
        self.selected_task_id = None
        self.memory_search_hints = None

    async def evaluate_search_depths(
        self,
        current_user_request,
        selected_task_id,
        memory_search_hints,
    ):
        self.current_user_request = current_user_request
        self.selected_task_id = selected_task_id
        self.memory_search_hints = memory_search_hints
        return types.SearchDepthDecision(
            depths={
                "task_catalog": types.SearchDepthTimestamps(
                    created_after="2026-01-01T00:00:00Z",
                    read_after="2026-01-01T00:00:00Z",
                    updated_after="2026-01-01T00:00:00Z",
                ),
                "past_conversation_context": types.SearchDepthTimestamps(
                    created_after="2026-07-01T00:00:00Z",
                    read_after="2026-07-01T00:00:00Z",
                    updated_after="2026-07-01T00:00:00Z",
                ),
            }
        )


class RecordingMemoryRetrieval:
    def __init__(self):
        self.memory_search_hints = None
        self.search_depths = None

    async def retrieve(self, memory_search_hints, search_depths):
        self.memory_search_hints = memory_search_hints
        self.search_depths = search_depths
        return RetrievedMemoryContext()


class RecordingMemoryRelevance:
    def __init__(self):
        self.current_user_request = None
        self.selected_task_id = None
        self.retrieved_memories = None

    async def evaluate_relevant_memories(
        self,
        current_user_request,
        selected_task_id,
        retrieved_memories,
    ):
        self.current_user_request = current_user_request
        self.selected_task_id = selected_task_id
        self.retrieved_memories = retrieved_memories
        return types.RelevantMemoryDecision(kept_memory_ids=[])


class VoiceRoutingTests(unittest.IsolatedAsyncioTestCase):
    def test_wake_keyword_is_removed_from_routed_transcript(self):
        matcher = TriggerPhraseMatcher(TriggerPhraseConfig())

        detection = matcher.match("Jarvis, do this.")

        self.assertIsNotNone(detection)
        self.assertEqual(detection.routed_transcript, "do this")

    def test_wake_keyword_aliases_are_removed_from_routed_transcript(self):
        matcher = TriggerPhraseMatcher(TriggerPhraseConfig())

        cases = (
            "Java, do this.",
            "Travis, do this.",
            "Jervis, do this.",
            "Jar vice, do this.",
            "Jar vis, do this.",
        )
        for transcript in cases:
            with self.subTest(transcript=transcript):
                detection = matcher.match(transcript)

                self.assertIsNotNone(detection)
                self.assertEqual(detection.phrase, "jarvis")
                self.assertEqual(detection.routed_transcript, "do this")

    async def test_task_choice_receives_routed_transcript(self):
        planner = RecordingPlanner()
        conversation_evaluation = RecordingConversationEvaluation()
        search_depth = RecordingSearchDepth()
        memory_retrieval = RecordingMemoryRetrieval()
        memory_relevance = RecordingMemoryRelevance()
        processor = VoiceTurnProcessor(
            config=_voice_config(),
            transcriber=StubTranscriber(),
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            planner=planner,
            conversation_evaluation=conversation_evaluation,
            search_depth=search_depth,
            memory_retrieval=memory_retrieval,
            memory_relevance=memory_relevance,
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
        self.assertEqual(search_depth.current_user_request, "do this")
        self.assertEqual(search_depth.selected_task_id, "task:needs_more_information")
        self.assertEqual(
            result.search_depths.depths["task_catalog"].created_after,
            "2026-01-01T00:00:00Z",
        )
        self.assertIs(memory_retrieval.memory_search_hints, result.memory_search_hints)
        self.assertIs(memory_retrieval.search_depths, result.search_depths)
        self.assertEqual(
            result.retrieved_memories.to_dict(),
            RetrievedMemoryContext().to_dict(),
        )
        self.assertEqual(memory_relevance.current_user_request, "do this")
        self.assertEqual(memory_relevance.selected_task_id, "task:needs_more_information")
        self.assertIs(memory_relevance.retrieved_memories, result.retrieved_memories)
        self.assertEqual(result.relevance_decision.kept_memory_ids, [])
        self.assertEqual(
            result.relevant_memories.to_dict(),
            RetrievedMemoryContext().to_dict(),
        )


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
