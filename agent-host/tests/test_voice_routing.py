import contextlib
import asyncio
import io
import time
import unittest
from argparse import Namespace
from dataclasses import dataclass
from threading import Event
from unittest.mock import patch

import numpy as np

from baml_sdk import context as baml_context
from baml_sdk import memory_search as baml_memory_search
from baml_sdk import memory_selection as baml_memory_selection
from baml_sdk import retrieved_memory as baml_retrieved_memory
from baml_sdk import task_completion as baml_task_completion
from baml_sdk import task_execution as baml_task_execution
from baml_sdk import task_prompt as baml_task_prompt
from baml_sdk import task_routing as baml_task_routing
from baml_sdk import voice_turn as baml_voice_turn
from reframe_agent_host.agent_flow.live_conversation import LiveConversationContext
from reframe_agent_host.commands.voice_output import VoiceTurnEventPrinter
from reframe_agent_host.commands.voice_turn import _ensure_voice_memory_context, run_voice_turn
from reframe_agent_host.memory_readiness import MemoryReadinessError
from reframe_agent_host.keyphrases import KeyphraseDetection, KeyphraseSpotterConfig
from reframe_agent_host.speech.transcription import (
    CONVERSATION_ON_CONFIRMATION_PROMPT,
    Transcript,
    WhisperTranscriberConfig,
)
from reframe_agent_host.speech.triggers import TriggerPhraseConfig, TriggerPhraseMatcher
from reframe_agent_host.voice.activity import DetectedUtterance, VoiceActivityConfig
from reframe_agent_host.voice.conversation_mode import ConversationModeController
from reframe_agent_host.voice.microphone import AudioInputConfig
from reframe_agent_host.voice.pipeline import VoiceTurnPipeline
from reframe_agent_host.voice.turn_processor import VoiceTurnProcessor
from reframe_agent_host.voice.capture_types import CaptureResult, VoiceTurnControl
from reframe_agent_host.voice.pipeline_config import VoicePipelineConfig
from reframe_agent_host.task_execution import (
    PrimitiveDispatchRecord,
    PrimitiveDispatchResult,
)
from reframe_memory import RetrievedMemoryContext


class StubTranscriber:
    def __init__(self, text="jarvis do this"):
        self.text = text
        self.prompts = []

    def transcribe(self, _samples, _sample_rate):
        return Transcript(
            text=self.text,
            language="en",
            duration_seconds=1.0,
            segments=[],
        )

    def transcribe_with_prompt(self, samples, sample_rate, initial_prompt):
        self.prompts.append(initial_prompt)
        return self.transcribe(samples, sample_rate)


class CountingStubTranscriber(StubTranscriber):
    def __init__(self, text="jarvis do this"):
        super().__init__(text)
        self.calls = 0

    def transcribe(self, samples, sample_rate):
        self.calls += 1
        return super().transcribe(samples, sample_rate)


class RecordingMemoryRetrieval:
    def __init__(self):
        self.memory_search_hints = None
        self.search_depths = None

    async def retrieve(self, memory_search_hints, search_depths):
        self.memory_search_hints = memory_search_hints
        self.search_depths = search_depths
        return RetrievedMemoryContext()


class RecordingBamlTurnFlow:
    def __init__(self):
        self.understanding_request = None
        self.continuation_request = None

    async def understand_prompt(self, current_user_request):
        self.understanding_request = current_user_request
        task_choice = baml_task_routing.TaskChoiceDecision(
            selected_task_id="task:needs_more_information",
            confidence=1.0,
            candidate_memory=None,
        )
        return baml_voice_turn.VoicePromptUnderstanding(
            task_choice=task_choice,
            selected_task=baml_task_routing.SelectedTaskContext(
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
            memory_search_hints=baml_memory_search.ConversationMemorySearchHints(
                tags=baml_memory_search.MemoryTagSearch(any_of=["test"], all_of=[], none_of=[]),
                strings=baml_memory_search.MemoryStringSearch(contains=["do this"], equals=[]),
                candidate_memory=None,
            ),
            search_depths=baml_memory_search.SearchDepthDecision(
                depths={
                    "task_catalog": baml_memory_search.SearchDepthTimestamps(
                        created_after="2026-01-01T00:00:00Z",
                        read_after="2026-01-01T00:00:00Z",
                        updated_after="2026-01-01T00:00:00Z",
                    )
                },
                candidate_memory=None,
            ),
            timings=baml_voice_turn.VoicePromptUnderstandingTimings(
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
        return baml_voice_turn.VoicePromptContinuation(
            relevance_decision=baml_memory_selection.RelevantMemoryDecision(
                kept_memory_ids=[],
                candidate_memory=None,
            ),
            selected_memories=baml_retrieved_memory.RetrievedMemoryGraph(
                task_catalog=[],
                past_sessions=[],
                current_session_memories=[],
            ),
            selected_memory_contexts=[],
            task_prompt=baml_task_prompt.TaskPromptDecision(
                full_task_prompt="Task:\nAsk only for what matters.\n\nInput:\nDo this.",
                candidate_memory=None,
            ),
            timings=baml_voice_turn.VoicePromptContinuationTimings(
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


class FakeCatalogStore:
    def __init__(self, ready):
        self.ready = ready

    async def search(self, mark_read=True):
        return [FakeNode("memory_node:catalog")] if self.ready else []


class MinimalVoiceMemoryDatabase:
    def __init__(self, *, roots_ready=True, catalog_ready=True):
        self.sessions = FakeSessions()
        self.conversations = FakeVoiceContextConversations()
        self.providers = FakeCatalogStore(catalog_ready)
        self.tasks = FakeCatalogStore(catalog_ready)
        self.closed = False
        self.roots_ready = roots_ready
        self.setup_calls = []

    async def query(self, _statement, _variables=None):
        return [{"id": "memory_root:test"}] if self.roots_ready else []

    async def apply_schema(self):
        self.setup_calls.append("apply_schema")

    async def ensure_roots(self):
        self.setup_calls.append("ensure_roots")

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
        self.providers = FakeCatalogStore(True)
        self.tasks = FakeCatalogStore(True)
        self.closed = False

    async def query(self, _statement, _variables=None):
        return [{"id": "memory_root:test"}]

    async def apply_schema(self):
        raise AssertionError("runtime should not apply memory schema")

    async def ensure_roots(self):
        raise AssertionError("runtime should not ensure memory roots")

    async def close(self):
        self.closed = True


class RecordingConversationMessages:
    def __init__(self):
        self.messages = []
        self.message_added = Event()

    async def add_message(self, conversation_id, message):
        self.messages.append((conversation_id, message.role, message.content))
        self.message_added.set()


class RecordingTurnMemoryDatabase:
    def __init__(self):
        self.conversations = RecordingConversationMessages()
        self.closed = Event()

    async def apply_schema(self):
        return None

    async def ensure_roots(self):
        return None

    async def close(self):
        self.closed.set()


class ClosingOnlyDatabase:
    async def close(self):
        return None


class RecordingTaskExecution:
    async def execute_task(self, **_kwargs):
        return baml_task_execution.TaskExecutionResult(
            returns=[
                baml_task_execution.TaskReturnItem(
                    name="agent_reply",
                    payload={"text": "What detail should I use?"},
                ),
            ],
        )


class FakeInterruptSpeaker:
    def __init__(self):
        self.calls = []
        self.active = True

    def interrupt(self, reason="human voice"):
        self.calls.append(reason)
        self.active = False
        return True

    def is_speaking(self):
        return self.active


class FakeBargeInDetector:
    def __init__(self):
        self.calls = []

    def accept(self, frame, *, tts_active, **_kwargs):
        self.calls.append((len(frame), tts_active))
        return tts_active


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
            conversation_mode=baml_context.ConversationMode.WAKE_COMMAND,
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
            conversation_mode=baml_context.ConversationMode.WAKE_COMMAND,
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
                conversation_mode=baml_context.ConversationMode.WAKE_COMMAND,
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
                conversation_mode=baml_context.ConversationMode.WAKE_COMMAND,
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

    async def test_cancelled_speculative_turn_does_not_start_transcription_during_grace(self):
        transcriber = CountingStubTranscriber("Jarvis, do this.")
        events = []
        processor = VoiceTurnProcessor(
            config=_voice_config(task_choice_enabled=False),
            transcriber=transcriber,
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            memory_retrieval=RecordingMemoryRetrieval(),
        )
        control = VoiceTurnControl()

        with patch(
            "reframe_agent_host.voice.turn_processor."
            "SPECULATIVE_TRANSCRIPTION_GRACE_SECONDS",
            0.1,
        ):
            task = asyncio.create_task(
                processor.process(
                    capture=_capture_result(),
                    conversation_mode=baml_context.ConversationMode.WAKE_COMMAND,
                    model_prepare_seconds=0.0,
                    total_started_at=time.perf_counter(),
                    on_event=lambda stage, message: events.append((stage, message)),
                    turn_control=control,
                )
            )

            await asyncio.sleep(0.02)
            control.cancel()

            with self.assertRaises(asyncio.CancelledError):
                await task

        self.assertEqual(transcriber.calls, 0)
        self.assertNotIn("transcribing", [stage for stage, _message in events])

    async def test_human_reply_outputs_before_background_database_write(self):
        database = RecordingTurnMemoryDatabase()
        turn_flow = RecordingBamlTurnFlow()
        events = []
        processor = VoiceTurnProcessor(
            config=_voice_config(
                session_id="memory_node:session",
                conversation_id="memory_node:conversation",
            ),
            transcriber=StubTranscriber("Jarvis, do this."),
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            memory_retrieval=RecordingMemoryRetrieval(),
            turn_flow=turn_flow,
        )

        async def fake_open_memory_database():
            return database

        with patch(
            "reframe_agent_host.voice.turn_side_effects.open_memory_database",
            fake_open_memory_database,
        ):
            await processor.process(
                capture=_capture_result(),
                conversation_mode=baml_context.ConversationMode.WAKE_COMMAND,
                model_prepare_seconds=0.0,
                total_started_at=time.perf_counter(),
                on_event=lambda stage, message: events.append((stage, message)),
            )
            self.assertTrue(database.conversations.message_added.wait(timeout=1))
            self.assertTrue(database.closed.wait(timeout=1))

        stages = [stage for stage, _message in events]
        self.assertLess(
            stages.index("human-reply"),
            stages.index("turn-understanding"),
        )
        self.assertEqual(
            database.conversations.messages,
            [("memory_node:conversation", "human", "do this")],
        )

    async def test_live_conversation_sees_human_reply_before_task_choice(self):
        database = RecordingTurnMemoryDatabase()
        live_conversation = LiveConversationContext()
        turn_flow = RecordingBamlTurnFlow()
        events = []
        processor = VoiceTurnProcessor(
            config=_voice_config(
                session_id="memory_node:session",
                conversation_id="memory_node:conversation",
            ),
            transcriber=StubTranscriber("Jarvis, do this."),
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            memory_retrieval=RecordingMemoryRetrieval(),
            turn_flow=turn_flow,
            live_conversation=live_conversation,
        )

        async def fake_open_memory_database():
            return database

        with patch(
            "reframe_agent_host.voice.turn_side_effects.open_memory_database",
            fake_open_memory_database,
        ):
            await processor.process(
                capture=_capture_result(),
                conversation_mode=baml_context.ConversationMode.WAKE_COMMAND,
                model_prepare_seconds=0.0,
                total_started_at=time.perf_counter(),
                on_event=lambda stage, message: events.append((stage, message)),
            )
            self.assertTrue(database.conversations.message_added.wait(timeout=1))

        conversation = live_conversation.merge(None, "memory_node:conversation")
        self.assertIsNotNone(conversation)
        self.assertEqual(
            [(message.role, message.content) for message in conversation.messages],
            [("human", "do this")],
        )

    async def test_empty_task_execution_result_skips_later_dispatch_layers(self):
        events = []
        processor = VoiceTurnProcessor(
            config=_voice_config(),
            transcriber=StubTranscriber("Jarvis, do this."),
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            memory_retrieval=RecordingMemoryRetrieval(),
        )

        async def fail_open_memory_database():
            raise AssertionError("empty task result should not dispatch primitives")

        with patch(
            "reframe_agent_host.voice.turn_side_effects.open_memory_database",
            fail_open_memory_database,
        ):
            result = await processor._side_effects.dispatch_primitives(
                baml_task_execution.TaskExecutionResult(returns=[]),
                time.perf_counter(),
                lambda stage, message: events.append((stage, message)),
            )

        self.assertEqual(result, (None, None, None))
        self.assertNotIn("primitive-dispatch", [stage for stage, _message in events])

    async def test_completion_review_runs_after_dispatched_primitives_and_summary(self):
        order = []
        completion_inputs = {}
        events = []
        processor = VoiceTurnProcessor(
            config=_voice_config(),
            transcriber=StubTranscriber("Jarvis, do this."),
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            memory_retrieval=RecordingMemoryRetrieval(),
            task_execution=RecordingTaskExecution(),
            turn_flow=RecordingBamlTurnFlow(),
        )

        class OrderedPrimitiveDispatcher:
            def __init__(self, **_kwargs):
                pass

            async def dispatch(self, _result):
                order.append("dispatch-start")
                await asyncio.sleep(0)
                order.append("dispatch-end")
                return PrimitiveDispatchResult(
                    records=(
                        PrimitiveDispatchRecord(
                            name="agent_reply",
                            status="ok",
                            detail="What detail should I use?",
                            output={"status": "ok"},
                        ),
                    ),
                    task_history_id="memory_node:task_history",
                    task_history_node_id="memory_node:task_history_node",
                )

        class OrderedActionHistorySummarizer:
            def __init__(self, **_kwargs):
                pass

            async def summarize(self, *_args, **_kwargs):
                order.append("summary-start")
                await asyncio.sleep(0)
                order.append("summary-end")
                return "The recorded actions asked the user a question."

            async def close(self):
                order.append("summary-close")

        class OrderedTaskCompletionChecker:
            async def check(self, **kwargs):
                order.append("review-start")
                completion_inputs.update(kwargs)
                await asyncio.sleep(0)
                order.append("review-end")
                return baml_task_completion.CompletionResult.PASS

        async def fake_open_memory_database():
            return ClosingOnlyDatabase()

        with patch(
            "reframe_agent_host.voice.turn_side_effects.PrimitiveDispatcher",
            OrderedPrimitiveDispatcher,
        ):
            with patch(
                "reframe_agent_host.voice.turn_side_effects.ActionHistorySummarizer",
                OrderedActionHistorySummarizer,
            ):
                with patch(
                    "reframe_agent_host.voice.turn_side_effects.TaskCompletionChecker",
                    OrderedTaskCompletionChecker,
                ):
                    with patch(
                        "reframe_agent_host.voice.turn_side_effects.open_memory_database",
                        fake_open_memory_database,
                    ):
                        result = await processor.process(
                            capture=_capture_result(),
                            conversation_mode=baml_context.ConversationMode.WAKE_COMMAND,
                            model_prepare_seconds=0.0,
                            total_started_at=time.perf_counter(),
                            on_event=lambda stage, message: events.append(
                                (stage, message),
                            ),
                        )

        self.assertLess(order.index("dispatch-end"), order.index("summary-start"))
        self.assertLess(order.index("summary-end"), order.index("review-start"))
        self.assertEqual(completion_inputs["completion_string"], "Question")
        self.assertEqual(
            completion_inputs["output_summary"],
            "The recorded actions asked the user a question.",
        )
        self.assertEqual(result.task_completion, baml_task_completion.CompletionResult.PASS)
        self.assertEqual(
            [stage for stage, _message in events if stage.endswith("reviewed")],
            ["task-completion-reviewed"],
        )

    async def test_conversation_on_confirmation_turns_mode_on_without_human_reply(self):
        transcriber = StubTranscriber("conversation on")
        mode_controller = ConversationModeController(baml_context.ConversationMode.WAKE_COMMAND)
        events = []
        processor = VoiceTurnProcessor(
            config=_voice_config(),
            transcriber=transcriber,
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            memory_retrieval=RecordingMemoryRetrieval(),
            mode_controller=mode_controller,
        )

        result = await processor.process(
            capture=_conversation_on_confirmation_capture(),
            conversation_mode=baml_context.ConversationMode.WAKE_COMMAND,
            model_prepare_seconds=0.0,
            total_started_at=time.perf_counter(),
            on_event=lambda stage, message: events.append((stage, message)),
        )

        self.assertTrue(result.mode_switched)
        self.assertEqual(result.routed_transcript, "")
        self.assertEqual(
            mode_controller.get(),
            baml_context.ConversationMode.CONTINUOUS_CONVERSATION,
        )
        self.assertEqual(transcriber.prompts, [CONVERSATION_ON_CONFIRMATION_PROMPT])
        self.assertNotIn("human-reply", [stage for stage, _message in events])
        self.assertIn(
            (
                "conversation-mode",
                baml_context.ConversationMode.CONTINUOUS_CONVERSATION.value,
            ),
            events,
        )

    async def test_conversation_on_confirmation_rejects_without_human_reply(self):
        transcriber = StubTranscriber("open the browser")
        mode_controller = ConversationModeController(baml_context.ConversationMode.WAKE_COMMAND)
        events = []
        processor = VoiceTurnProcessor(
            config=_voice_config(),
            transcriber=transcriber,
            trigger_matcher=TriggerPhraseMatcher(TriggerPhraseConfig()),
            memory_retrieval=RecordingMemoryRetrieval(),
            mode_controller=mode_controller,
        )

        result = await processor.process(
            capture=_conversation_on_confirmation_capture(),
            conversation_mode=baml_context.ConversationMode.WAKE_COMMAND,
            model_prepare_seconds=0.0,
            total_started_at=time.perf_counter(),
            on_event=lambda stage, message: events.append((stage, message)),
        )

        self.assertTrue(result.ignored)
        self.assertEqual(
            mode_controller.get(),
            baml_context.ConversationMode.WAKE_COMMAND,
        )
        self.assertEqual(transcriber.prompts, [CONVERSATION_ON_CONFIRMATION_PROMPT])
        self.assertNotIn("human-reply", [stage for stage, _message in events])
        self.assertIn("turn-ignored", [stage for stage, _message in events])

    def test_cli_prints_input_lifecycle_events_in_normal_mode(self):
        output = io.StringIO()
        printer = VoiceTurnEventPrinter(
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

    def test_barge_in_frame_handler_only_interrupts_active_tts_once(self):
        pipeline = object.__new__(VoiceTurnPipeline)
        speaker = FakeInterruptSpeaker()
        detector = FakeBargeInDetector()
        pipeline._speaker = speaker
        pipeline._barge_in_detector = detector
        events = []

        pipeline._handle_tts_barge_in_frame(
            np.zeros(512, dtype=np.float32),
            lambda stage, message: events.append((stage, message)),
        )
        pipeline._handle_tts_barge_in_frame(
            np.zeros(512, dtype=np.float32),
            lambda stage, message: events.append((stage, message)),
        )

        self.assertEqual(speaker.calls, ["human voice"])
        self.assertEqual(detector.calls, [(512, True), (512, False)])
        self.assertEqual(
            events,
            [
                ("barge-in", "human voice"),
            ],
        )

    def test_cli_prints_startup_latency_only_once(self):
        output = io.StringIO()
        printer = VoiceTurnEventPrinter(
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
        printer = VoiceTurnEventPrinter(
            debug_output=False,
            turn_started_at=time.perf_counter(),
        )

        with contextlib.redirect_stdout(output):
            printer("task-chosen", "selected: Reply to user (5.264s)")

        self.assertEqual(output.getvalue().splitlines(), [
            "selected: Reply to user",
            "[task_choice 5.264s]",
        ])

    def test_cli_prints_agent_reply_interrupted(self):
        output = io.StringIO()
        printer = VoiceTurnEventPrinter(
            debug_output=False,
            turn_started_at=time.perf_counter(),
        )

        with contextlib.redirect_stdout(output):
            printer(
                "agent-reply-interrupted",
                "Last fully spoken word beta at character 10",
            )

        self.assertEqual(output.getvalue().splitlines(), [
            "agent_reply_interrupted: Last fully spoken word beta at character 10",
        ])

    def test_cli_prints_barge_in_event(self):
        output = io.StringIO()
        printer = VoiceTurnEventPrinter(
            debug_output=False,
            turn_started_at=time.perf_counter(),
        )

        with contextlib.redirect_stdout(output):
            printer("barge-in", "human voice")

        self.assertEqual(output.getvalue().splitlines(), [
            "[barge-in] human voice",
        ])

    def test_cli_prints_conversation_mode_status_lines(self):
        output = io.StringIO()
        printer = VoiceTurnEventPrinter(
            debug_output=False,
            turn_started_at=time.perf_counter(),
        )

        with contextlib.redirect_stdout(output):
            printer("conversation-mode", "continuous_conversation")
            printer("conversation-mode", "continuous conversation off")
            printer("conversation-mode", "wake_command")
            printer("conversation-mode", "continuous_conversation")

        self.assertEqual(output.getvalue().splitlines(), [
            "[conversation mode] On",
            "[conversation mode] Off",
            "[conversation mode] On",
        ])

    def test_cli_prints_prompt_layer_latencies_from_baml_flow_events(self):
        output = io.StringIO()
        printer = VoiceTurnEventPrinter(
            debug_output=False,
            turn_started_at=time.perf_counter(),
        )

        with contextlib.redirect_stdout(output):
            printer("memory-search-hints", "{} (0.120s)")
            printer("search-depths", "{} (0.085s)")
            printer("memory-relevance-decision", "{} (0.090s)")
            printer("task-prompt-generated", "64 chars (0.240s)")
            printer("action-history-summarized", "42 chars (0.110s)")
            printer("task-completion-reviewed", "PASS (0.075s)")

        self.assertEqual(output.getvalue().splitlines(), [
            "[memory_search 120ms]",
            "[search_depth 85ms]",
            "[memory_relevance 90ms]",
            "[task_prompt 240ms]",
            "[action_history_summary 110ms]",
            "[task_completion 75ms]",
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
        self.assertEqual(database.setup_calls, [])

    async def test_voice_context_reports_unprepared_memory_without_setup(self):
        database = MinimalVoiceMemoryDatabase(roots_ready=False)
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
            with self.assertRaises(MemoryReadinessError):
                await _ensure_voice_memory_context(args)

        self.assertTrue(database.closed)
        self.assertEqual(database.setup_calls, [])

    async def test_voice_turn_prints_memory_readiness_error_and_quits(self):
        args = Namespace(
            turns=1,
            debug_output=False,
            verbose_context=False,
        )

        async def fail_config(_args):
            raise MemoryReadinessError("database is not ready")

        stderr = io.StringIO()
        with patch(
            "reframe_agent_host.commands.voice_turn._prepared_voice_pipeline_config",
            fail_config,
        ):
            with contextlib.redirect_stderr(stderr):
                code = await run_voice_turn(args)

        self.assertEqual(code, 5)
        self.assertEqual(stderr.getvalue().strip(), "[memory] database is not ready")

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


def _voice_config(
    task_choice_enabled=True,
    session_id=None,
    conversation_id=None,
):
    return VoicePipelineConfig(
        audio=AudioInputConfig(),
        voice_activity=VoiceActivityConfig(),
        keyphrases=KeyphraseSpotterConfig(),
        triggers=TriggerPhraseConfig(),
        transcription=WhisperTranscriberConfig(),
        conversation_mode=baml_context.ConversationMode.WAKE_COMMAND,
        task_choice_enabled=task_choice_enabled,
        session_id=session_id,
        conversation_id=conversation_id,
    )


def _capture_result():
    return CaptureResult(
        conversation_mode=baml_context.ConversationMode.WAKE_COMMAND,
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


def _conversation_on_confirmation_capture():
    return CaptureResult(
        conversation_mode=baml_context.ConversationMode.WAKE_COMMAND,
        keyphrase_detection=KeyphraseDetection(
            kind="conversation_on",
            phrase="conversation on",
            hypstr="conversation on",
            confirmed=True,
            phrase_start_sample=0,
            phrase_end_sample=1600,
        ),
        utterance=DetectedUtterance(
            samples=np.zeros(1600, dtype=np.float32),
            sample_rate=16_000,
            duration_seconds=0.1,
            forced_end=True,
        ),
        mode_switched=False,
        keyphrase_wait_seconds=0.0,
        listen_seconds=0.1,
        wait_for_speech_seconds=None,
        speech_capture_wall_seconds=0.1,
    )


if __name__ == "__main__":
    unittest.main()
