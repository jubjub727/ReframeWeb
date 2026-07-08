import contextlib
import asyncio
import io
import time
import unittest
from argparse import Namespace
from dataclasses import dataclass
from unittest.mock import patch

import numpy as np

import baml_sdk as types
from reframe_agent_host.commands.voice_turn import (
    _VoiceTurnEventPrinter,
    _ensure_voice_memory_context,
)
from reframe_agent_host.keyphrases import KeyphraseDetection, KeyphraseSpotterConfig
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


class RecordingMemoryRetrieval:
    def __init__(self):
        self.memory_search_hints = None
        self.search_depths = None

    async def retrieve(self, memory_search_hints, search_depths):
        self.memory_search_hints = memory_search_hints
        self.search_depths = search_depths
        return RetrievedMemoryContext()


class RecordingBamlTurnFlow:
    def __init__(self, agent_thought=None):
        self.agent_thought = agent_thought
        self.understanding_request = None
        self.continuation_request = None

    async def understand_prompt(self, current_user_request):
        self.understanding_request = current_user_request
        task_choice = types.TaskChoiceDecision(
            selected_task_id="task:needs_more_information",
            confidence=1.0,
            agent_thought=self.agent_thought,
            candidate_memory=None,
        )
        return types.VoicePromptUnderstanding(
            task_choice=task_choice,
            selected_task=types.SelectedTaskContext(
                id="task:needs_more_information",
                name="Needs more information",
                description="Ask for the missing detail.",
                input="User request",
                output="Question",
                prompt="Ask only for what matters.",
                provider_id="provider:test",
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
                read_at="2026-01-01T00:00:00Z",
            ),
            memory_search_hints=types.ConversationMemorySearchHints(
                tags=types.MemoryTagSearch(any_of=["test"], all_of=[], none_of=[]),
                strings=types.MemoryStringSearch(contains=["do this"], equals=[]),
                candidate_memory=None,
            ),
            search_depths=types.SearchDepthDecision(
                depths={
                    "task_catalog": types.SearchDepthTimestamps(
                        created_after="2026-01-01T00:00:00Z",
                        read_after="2026-01-01T00:00:00Z",
                        updated_after="2026-01-01T00:00:00Z",
                    )
                },
                candidate_memory=None,
            ),
            timings=types.VoicePromptUnderstandingTimings(
                task_choice_ms=5264,
                memory_search_ms=120,
                search_depth_ms=85,
            ),
        )

    async def continue_prompt(
        self,
        current_user_request,
        selected_task,
        retrieved_memories,
    ):
        self.continuation_request = (
            current_user_request,
            selected_task.id,
            retrieved_memories,
        )
        return types.VoicePromptContinuation(
            relevance_decision=types.RelevantMemoryDecision(
                kept_memory_ids=[],
                candidate_memory=None,
            ),
            selected_memories=types.RetrievedMemoryGraph(
                task_catalog=[],
                past_sessions=[],
                current_session_memories=[],
            ),
            selected_memory_contexts=[],
            task_prompt=types.TaskPromptDecision(
                full_task_prompt="Task:\nAsk only for what matters.\n\nInput:\nDo this.",
                candidate_memory=None,
            ),
            timings=types.VoicePromptContinuationTimings(
                memory_relevance_ms=90,
                task_prompt_ms=240,
            ),
        )


@dataclass
class FakeNode:
    id: str


class FakeSessions:
    async def create(self, _session, tags=()):
        return FakeNode("memory_node:session")


class FakeVoiceContextConversations:
    async def create(self, session_id, _conversation, tags=()):
        return FakeNode(f"{session_id}:conversation")


class MinimalVoiceMemoryDatabase:
    def __init__(self):
        self.sessions = FakeSessions()
        self.conversations = FakeVoiceContextConversations()
        self.closed = False

    async def apply_schema(self):
        return None

    async def ensure_roots(self):
        return None

    async def close(self):
        self.closed = True


class ExistingVoiceContextSessions:
    async def get(self, session_id, mark_read=True):
        if session_id == "memory_node:session":
            return FakeNode(session_id)
        return None

    async def conversations_for(self, session_id, mark_read=True):
        if session_id != "memory_node:session":
            return []
        return [FakeNode("memory_node:conversation")]


class ExistingVoiceMemoryDatabase:
    def __init__(self):
        self.sessions = ExistingVoiceContextSessions()
        self.closed = False

    async def apply_schema(self):
        return None

    async def ensure_roots(self):
        return None

    async def close(self):
        self.closed = True


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
            "Jarivs, do this.",
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

    def test_just_is_not_a_plain_wake_alias(self):
        matcher = TriggerPhraseMatcher(TriggerPhraseConfig())

        detection = matcher.match("Just tell me a joke.")

        self.assertIsNone(detection)

    def test_confirmed_wake_strips_whisper_just_residue(self):
        matcher = TriggerPhraseMatcher(TriggerPhraseConfig())

        detection = matcher.match_confirmed(
            "Just tell me a joke.",
            kind="wake_command",
            phrase="jarvis",
        )

        self.assertIsNotNone(detection)
        self.assertEqual(detection.phrase, "jarvis")
        self.assertEqual(detection.routed_transcript, "tell me a joke")

    def test_confirmed_wake_keeps_real_just_after_explicit_wake_word(self):
        matcher = TriggerPhraseMatcher(TriggerPhraseConfig())

        detection = matcher.match_confirmed(
            "Jarvis, just tell me a joke.",
            kind="wake_command",
            phrase="jarvis",
        )

        self.assertIsNotNone(detection)
        self.assertEqual(detection.routed_transcript, "just tell me a joke")

    async def test_baml_turn_flow_receives_routed_transcript(self):
        turn_flow = RecordingBamlTurnFlow()
        memory_retrieval = RecordingMemoryRetrieval()
        processor = VoiceTurnProcessor(
            config=_voice_config(),
            transcriber=StubTranscriber(),
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            memory_retrieval=memory_retrieval,
            turn_flow=turn_flow,
        )

        result = await processor.process(
            capture=_capture_result(),
            conversation_mode=types.ConversationMode.WAKE_COMMAND,
            model_prepare_seconds=0.0,
            total_started_at=time.perf_counter(),
            on_event=None,
        )

        self.assertEqual(result.transcript.text, "jarvis do this")
        self.assertEqual(result.routed_transcript, "do this")
        self.assertEqual(turn_flow.understanding_request, "do this")
        self.assertEqual(turn_flow.continuation_request[0], "do this")
        self.assertEqual(turn_flow.continuation_request[1], "task:needs_more_information")
        self.assertEqual(result.memory_search_hints.strings.contains, ["do this"])
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
        self.assertEqual(result.relevance_decision.kept_memory_ids, [])
        self.assertEqual(
            result.relevant_memories.to_dict(),
            RetrievedMemoryContext().to_dict(),
        )
        self.assertIn("Task:\nAsk only for what matters.", result.task_prompt.full_task_prompt)

    async def test_baml_turn_flow_owns_task_and_prompt_flow_when_present(self):
        turn_flow = RecordingBamlTurnFlow()
        memory_retrieval = RecordingMemoryRetrieval()
        processor = VoiceTurnProcessor(
            config=_voice_config(),
            transcriber=StubTranscriber(),
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            memory_retrieval=memory_retrieval,
            turn_flow=turn_flow,
        )

        result = await processor.process(
            capture=_capture_result(),
            conversation_mode=types.ConversationMode.WAKE_COMMAND,
            model_prepare_seconds=0.0,
            total_started_at=time.perf_counter(),
            on_event=None,
        )

        self.assertEqual(turn_flow.understanding_request, "do this")
        self.assertEqual(turn_flow.continuation_request[0], "do this")
        self.assertEqual(
            turn_flow.continuation_request[1],
            "task:needs_more_information",
        )
        self.assertIs(memory_retrieval.memory_search_hints, result.memory_search_hints)
        self.assertEqual(result.relevance_decision.kept_memory_ids, [])
        self.assertIn("Task:\nAsk only for what matters.", result.task_prompt.full_task_prompt)

    async def test_task_choice_agent_thought_is_emitted(self):
        turn_flow = RecordingBamlTurnFlow(agent_thought="Route this through the info task.")
        events = []
        processor = VoiceTurnProcessor(
            config=_voice_config(),
            transcriber=StubTranscriber(),
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            memory_retrieval=RecordingMemoryRetrieval(),
            turn_flow=turn_flow,
        )

        result = await processor.process(
            capture=_capture_result(),
            conversation_mode=types.ConversationMode.WAKE_COMMAND,
            model_prepare_seconds=0.0,
            total_started_at=time.perf_counter(),
            on_event=lambda stage, message: events.append((stage, message)),
        )

        self.assertEqual(
            result.task_choice.agent_thought,
            "Route this through the info task.",
        )
        self.assertIn(
            ("agent-thought", "Route this through the info task."),
            events,
        )

    async def test_speculative_turn_emits_human_reply_after_commit(self):
        events = []
        processor = VoiceTurnProcessor(
            config=_voice_config(task_choice_enabled=False),
            transcriber=StubTranscriber("Okay, nice."),
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            memory_retrieval=RecordingMemoryRetrieval(),
        )
        control = VoiceTurnControl()
        task = asyncio.create_task(
            processor.process(
                capture=_capture_result(),
                conversation_mode=types.ConversationMode.WAKE_COMMAND,
                model_prepare_seconds=0.0,
                total_started_at=time.perf_counter(),
                on_event=lambda stage, message: events.append((stage, message)),
                turn_control=control,
            )
        )

        await asyncio.sleep(0.05)
        self.assertNotIn(("human-reply", "Okay, nice."), events)

        control.commit()
        await task

        self.assertEqual(events.count(("human-reply", "Okay, nice.")), 1)

    async def test_speculative_turn_waits_for_commit_before_task_choice(self):
        turn_flow = RecordingBamlTurnFlow()
        events = []
        processor = VoiceTurnProcessor(
            config=_voice_config(),
            transcriber=StubTranscriber("Jarvis, do this."),
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            memory_retrieval=RecordingMemoryRetrieval(),
            turn_flow=turn_flow,
        )
        control = VoiceTurnControl()
        task = asyncio.create_task(
            processor.process(
                capture=_capture_result(),
                conversation_mode=types.ConversationMode.WAKE_COMMAND,
                model_prepare_seconds=0.0,
                total_started_at=time.perf_counter(),
                on_event=lambda stage, message: events.append((stage, message)),
                turn_control=control,
            )
        )

        await asyncio.sleep(0.05)
        self.assertIsNone(turn_flow.understanding_request)

        control.commit()
        await task

        self.assertEqual(turn_flow.understanding_request, "do this")
        stages = [stage for stage, _message in events]
        self.assertLess(stages.index("human-reply"), stages.index("turn-understanding"))

    def test_cli_prints_input_lifecycle_events_in_normal_mode(self):
        output = io.StringIO()
        printer = _VoiceTurnEventPrinter(
            debug_output=False,
            turn_started_at=time.perf_counter(),
        )

        with contextlib.redirect_stdout(output):
            printer("input-started", "microphone stream opened")
            printer("input-stopped", "microphone stream closed")

        self.assertEqual(output.getvalue().splitlines(), [
            "[Input Started]",
            "[Input Stopped]",
        ])

    def test_cli_prints_startup_latency_only_once(self):
        output = io.StringIO()
        printer = _VoiceTurnEventPrinter(
            debug_output=False,
            turn_started_at=10.0,
        )

        with patch("time.perf_counter", side_effect=[10.25, 120.0]):
            with contextlib.redirect_stdout(output):
                printer("listening", "first")
                printer("listening", "second")

        self.assertEqual(output.getvalue().splitlines(), [
            "[startup 250ms] ready",
            "[ready]",
        ])

    def test_cli_prints_selected_task_name(self):
        output = io.StringIO()
        printer = _VoiceTurnEventPrinter(
            debug_output=False,
            turn_started_at=time.perf_counter(),
        )

        with contextlib.redirect_stdout(output):
            printer("task-chosen", "selected: Reply to user (5.264s)")

        self.assertEqual(output.getvalue().splitlines(), [
            "selected: Reply to user",
            "[task_choice 5.264s]",
        ])

    def test_cli_prints_prompt_layer_latencies_from_baml_flow_events(self):
        output = io.StringIO()
        printer = _VoiceTurnEventPrinter(
            debug_output=False,
            turn_started_at=time.perf_counter(),
        )

        with contextlib.redirect_stdout(output):
            printer("memory-search-hints", "{} (0.120s)")
            printer("search-depths", "{} (0.085s)")
            printer("memory-relevance-decision", "{} (0.090s)")
            printer("task-prompt-generated", "64 chars (0.240s)")
            printer("action-history-summarized", "42 chars (0.110s)")

        self.assertEqual(output.getvalue().splitlines(), [
            "[memory_search 120ms]",
            "[search_depth 85ms]",
            "[memory_relevance 90ms]",
            "[task_prompt 240ms]",
            "[action_history_summary 110ms]",
        ])

    async def test_voice_context_setup_does_not_seed_core_tasks_by_default(self):
        database = MinimalVoiceMemoryDatabase()
        args = Namespace(
            session_id=None,
            conversation_id=None,
            debug_output=False,
            verbose_context=False,
        )

        async def fake_open_memory_database():
            return database

        with patch(
            "reframe_agent_host.commands.voice_turn.open_memory_database",
            fake_open_memory_database,
        ):
            await _ensure_voice_memory_context(args)

        self.assertEqual(args.session_id, "memory_node:session")
        self.assertEqual(
            args.conversation_id,
            "memory_node:session:conversation",
        )
        self.assertTrue(database.closed)

    async def test_voice_context_rejects_half_resume(self):
        args = Namespace(
            session_id="memory_node:session",
            conversation_id=None,
            debug_output=False,
            verbose_context=False,
        )

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                await _ensure_voice_memory_context(args)

        self.assertEqual(raised.exception.code, 2)

    async def test_voice_context_validates_explicit_resume_pair(self):
        database = ExistingVoiceMemoryDatabase()
        args = Namespace(
            session_id="memory_node:session",
            conversation_id="memory_node:conversation",
            debug_output=False,
            verbose_context=False,
        )

        async def fake_open_memory_database():
            return database

        with patch(
            "reframe_agent_host.commands.voice_turn.open_memory_database",
            fake_open_memory_database,
        ):
            await _ensure_voice_memory_context(args)

        self.assertTrue(database.closed)


def _voice_config(task_choice_enabled=True):
    return VoicePipelineConfig(
        audio=AudioInputConfig(),
        voice_activity=VoiceActivityConfig(),
        keyphrases=KeyphraseSpotterConfig(),
        triggers=TriggerPhraseConfig(),
        transcription=WhisperTranscriberConfig(),
        conversation_mode=types.ConversationMode.WAKE_COMMAND,
        task_choice_enabled=task_choice_enabled,
    )


def _capture_result():
    return CaptureResult(
        conversation_mode=types.ConversationMode.WAKE_COMMAND,
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
