from __future__ import annotations

import asyncio
import time
from threading import Thread

from reframe_agent_host.agent_flow.action_history import ActionHistorySummarizer
from reframe_agent_host.agent_flow.live_conversation import LiveConversationContext
from reframe_agent_host.agent_flow.retrieved_memory_graph import (
    BamlRetrievedMemoryContext,
)
from reframe_agent_host.agent_flow.task_completion import TaskCompletionChecker
from reframe_agent_host.agent_flow.task_execution import TaskExecutionPlanner
from baml_sdk import context as baml_context
from baml_sdk import memory_search as baml_memory_search
from baml_sdk import task_completion as baml_task_completion
from baml_sdk import task_execution as baml_task_execution
from baml_sdk import task_prompt as baml_task_prompt
from baml_sdk import task_routing as baml_task_routing
from reframe_agent_host.speech.transcription import (
    CONVERSATION_ON_CONFIRMATION_PROMPT,
    Transcriber,
    transcribe_with_initial_prompt,
)
from reframe_agent_host.speech.triggers import TriggerPhraseMatcher
from reframe_agent_host.speech.tts import NoopSpeaker, TextSpeaker
from reframe_agent_host.voice.conversation_mode import ConversationModeController
from reframe_agent_host.voice.daemon_threads import run_in_daemon_thread
from reframe_agent_host.task_execution import PrimitiveDispatcher
from reframe_agent_host.voice.turn_results import (
    ignored_turn_result,
    mode_switch_turn_result,
    transcribed_turn_result,
)
from reframe_agent_host.voice.types import (
    CaptureResult,
    VoicePipelineConfig,
    VoicePipelineEventHandler,
    VoiceTurnControl,
    VoiceTurnResult,
)
from reframe_agent_host.voice.utterance_quality import (
    should_ignore_continuous_utterance,
)
from reframe_memory import ConversationMessage, open_memory_database
from reframe_memory.retrieved_context import RetrievedMemoryContext


SPECULATIVE_TRANSCRIPTION_GRACE_SECONDS = 0.25


class VoiceTurnProcessor:
    def __init__(
        self,
        config: VoicePipelineConfig,
        transcriber: Transcriber,
        trigger_matcher: TriggerPhraseMatcher,
        memory_retrieval,
        task_execution: TaskExecutionPlanner | None = None,
        speaker: TextSpeaker | None = None,
        mode_controller: ConversationModeController | None = None,
        turn_flow=None,
        live_conversation: LiveConversationContext | None = None,
    ) -> None:
        self._config = config
        self._transcriber = transcriber
        self._trigger_matcher = trigger_matcher
        self._memory_retrieval = memory_retrieval
        self._task_execution = task_execution
        self._speaker = speaker or NoopSpeaker()
        self._mode_controller = mode_controller
        self._turn_flow = turn_flow
        self._live_conversation = live_conversation

    async def process(
        self,
        capture: CaptureResult,
        conversation_mode: baml_context.ConversationMode,
        model_prepare_seconds: float,
        total_started_at: float,
        on_event: VoicePipelineEventHandler | None,
        turn_control: VoiceTurnControl | None = None,
    ) -> VoiceTurnResult:
        if capture.mode_switched and capture.utterance is None:
            return mode_switch_turn_result(
                capture,
                conversation_mode,
                model_prepare_seconds,
                total_started_at,
            )

        if capture.utterance is None:
            raise RuntimeError("Capture finished without an utterance.")

        post_vad_started_at = time.perf_counter()
        utterance = capture.utterance
        if _is_continuous_unprompted(conversation_mode, capture):
            ignored, quality = should_ignore_continuous_utterance(
                utterance.samples,
                utterance.sample_rate,
            )
            if ignored:
                await self._wait_until_committed(turn_control)
                self._emit(
                    on_event,
                    "turn-ignored",
                    (
                        "continuous-mode noise gate "
                        f"peak={quality.peak:.3f} "
                        f"active_rms={quality.active_rms:.3f} "
                        f"active_ms={quality.active_ms:.0f}"
                    ),
                )
                return ignored_turn_result(
                    self._config,
                    capture,
                    conversation_mode,
                    model_prepare_seconds,
                    total_started_at,
                )

        if _is_conversation_on_confirmation(capture):
            return await self._process_conversation_on_confirmation(
                capture=capture,
                conversation_mode=conversation_mode,
                model_prepare_seconds=model_prepare_seconds,
                total_started_at=total_started_at,
                on_event=on_event,
                turn_control=turn_control,
            )

        await self._wait_for_speculative_transcription_start(turn_control)
        self._emit(
            on_event,
            "transcribing",
            f"{utterance.duration_seconds:.2f}s utterance with {_transcriber_label(self._transcriber)}",
        )
        transcription_started_at = time.perf_counter()
        transcript = await run_in_daemon_thread(
            self._transcriber.transcribe,
            utterance.samples,
            utterance.sample_rate,
        )
        transcription_seconds = time.perf_counter() - transcription_started_at
        await self._checkpoint(turn_control)
        self._emit(
            on_event,
            "transcript",
            f"{transcript.text or '<empty>'} ({transcription_seconds:.3f}s)",
        )

        trigger_detection = self._match_trigger(transcript.text, capture)
        routed_transcript = (
            trigger_detection.routed_transcript
            if trigger_detection is not None
            else transcript.text
        )
        if _is_conversation_on_trigger_only(trigger_detection):
            await self._wait_until_committed(turn_control)
            mode = self._turn_on_conversation_mode(on_event)
            return mode_switch_turn_result(
                _mode_switch_capture(capture, mode),
                mode,
                model_prepare_seconds,
                total_started_at,
            )

        await self._wait_until_committed(turn_control)
        if routed_transcript:
            self._remember_live_human_reply(routed_transcript)
            self._emit(on_event, "human-reply", routed_transcript)
            self._record_human_reply_in_background(routed_transcript, on_event)
        if trigger_detection is not None:
            self._emit(
                on_event,
                "trigger",
                f"{trigger_detection.kind} {trigger_detection.phrase!r}",
            )

        return await self._process_with_baml_flow(
            capture=capture,
            conversation_mode=conversation_mode,
            model_prepare_seconds=model_prepare_seconds,
            total_started_at=total_started_at,
            on_event=on_event,
            turn_control=turn_control,
            transcript=transcript,
            trigger_detection=trigger_detection,
            routed_transcript=routed_transcript,
            post_vad_started_at=post_vad_started_at,
            transcription_seconds=transcription_seconds,
        )

    def _match_trigger(self, transcript: str, capture: CaptureResult):
        if capture.keyphrase_detection is None:
            return self._trigger_matcher.match(transcript)
        return self._trigger_matcher.match_confirmed(
            transcript,
            capture.keyphrase_detection.kind,
            capture.keyphrase_detection.phrase,
        )

    async def _checkpoint(self, turn_control: VoiceTurnControl | None) -> None:
        if turn_control is not None:
            await turn_control.checkpoint()

    async def _wait_until_committed(
        self,
        turn_control: VoiceTurnControl | None,
    ) -> None:
        if turn_control is not None:
            await turn_control.wait_until_committed()

    async def _wait_for_speculative_transcription_start(
        self,
        turn_control: VoiceTurnControl | None,
    ) -> None:
        if turn_control is not None:
            await turn_control.wait_for_commit_or_cancel(
                SPECULATIVE_TRANSCRIPTION_GRACE_SECONDS,
            )

    async def close(self) -> None:
        for component in (
            self._memory_retrieval,
            self._task_execution,
            self._turn_flow,
        ):
            close = getattr(component, "close", None)
            if close is not None:
                await close()

    async def _process_with_baml_flow(
        self,
        *,
        capture: CaptureResult,
        conversation_mode: baml_context.ConversationMode,
        model_prepare_seconds: float,
        total_started_at: float,
        on_event: VoicePipelineEventHandler | None,
        turn_control: VoiceTurnControl | None,
        transcript,
        trigger_detection,
        routed_transcript: str,
        post_vad_started_at: float,
        transcription_seconds: float,
    ) -> VoiceTurnResult:
        if not self._config.task_choice_enabled:
            post_vad_transcript_seconds = time.perf_counter() - post_vad_started_at
            return transcribed_turn_result(
                config=self._config,
                conversation_mode=conversation_mode,
                capture=capture,
                transcript=transcript,
                trigger_detection=trigger_detection,
                routed_transcript=routed_transcript,
                task_choice=None,
                memory_search_hints=None,
                search_depths=None,
                retrieved_memories=None,
                relevance_decision=None,
                relevant_memories=None,
                selected_memory_contexts=None,
                task_prompt=None,
                task_execution=None,
                primitive_dispatch=None,
                action_history_summary=None,
                task_completion=None,
                timings={
                    "model_prepare_seconds": model_prepare_seconds,
                    "total_started_at": total_started_at,
                    "post_vad_transcript_seconds": post_vad_transcript_seconds,
                    "post_vad_task_choice_seconds": None,
                    "post_vad_memory_search_seconds": None,
                    "post_vad_search_depth_seconds": None,
                    "post_vad_memory_retrieval_seconds": None,
                    "post_vad_memory_relevance_seconds": None,
                    "post_vad_task_prompt_seconds": None,
                    "post_vad_task_execution_seconds": None,
                    "post_vad_primitive_dispatch_seconds": None,
                    "post_vad_action_history_summary_seconds": None,
                    "post_vad_task_completion_seconds": None,
                    "transcription_seconds": transcription_seconds,
                    "task_choice_seconds": None,
                    "memory_search_seconds": None,
                    "search_depth_seconds": None,
                    "memory_retrieval_seconds": None,
                    "memory_relevance_seconds": None,
                    "task_prompt_seconds": None,
                    "task_execution_seconds": None,
                    "primitive_dispatch_seconds": None,
                    "action_history_summary_seconds": None,
                    "task_completion_seconds": None,
                },
            )

        if not routed_transcript:
            self._emit(on_event, "task-choice", "skipped empty transcript")
            post_vad_transcript_seconds = time.perf_counter() - post_vad_started_at
            return transcribed_turn_result(
                config=self._config,
                conversation_mode=conversation_mode,
                capture=capture,
                transcript=transcript,
                trigger_detection=trigger_detection,
                routed_transcript=routed_transcript,
                task_choice=None,
                memory_search_hints=None,
                search_depths=None,
                retrieved_memories=None,
                relevance_decision=None,
                relevant_memories=None,
                selected_memory_contexts=None,
                task_prompt=None,
                task_execution=None,
                primitive_dispatch=None,
                action_history_summary=None,
                task_completion=None,
                timings={
                    "model_prepare_seconds": model_prepare_seconds,
                    "total_started_at": total_started_at,
                    "post_vad_transcript_seconds": post_vad_transcript_seconds,
                    "post_vad_task_choice_seconds": None,
                    "post_vad_memory_search_seconds": None,
                    "post_vad_search_depth_seconds": None,
                    "post_vad_memory_retrieval_seconds": None,
                    "post_vad_memory_relevance_seconds": None,
                    "post_vad_task_prompt_seconds": None,
                    "post_vad_task_execution_seconds": None,
                    "post_vad_primitive_dispatch_seconds": None,
                    "post_vad_action_history_summary_seconds": None,
                    "post_vad_task_completion_seconds": None,
                    "transcription_seconds": transcription_seconds,
                    "task_choice_seconds": None,
                    "memory_search_seconds": None,
                    "search_depth_seconds": None,
                    "memory_retrieval_seconds": None,
                    "memory_relevance_seconds": None,
                    "task_prompt_seconds": None,
                    "task_execution_seconds": None,
                    "primitive_dispatch_seconds": None,
                    "action_history_summary_seconds": None,
                    "task_completion_seconds": None,
                },
            )

        if self._turn_flow is None:
            raise RuntimeError("Voice prompt processing requires a BAML turn flow.")

        self._emit(
            on_event,
            "turn-understanding",
            "understanding task and memory needs with BAML",
        )
        understanding = await self._turn_flow.understand_prompt(
            routed_transcript,
        )
        post_vad_understanding_seconds = time.perf_counter() - post_vad_started_at
        task_choice = understanding.task_choice
        selected_task = understanding.selected_task
        memory_search_hints = understanding.memory_search_hints
        search_depths = understanding.search_depths
        task_choice_seconds = _seconds_from_ms(
            understanding.timings.task_choice_ms,
        )
        memory_search_seconds = _seconds_from_ms(
            understanding.timings.memory_search_ms,
        )
        search_depth_seconds = _seconds_from_ms(
            understanding.timings.search_depth_ms,
        )

        self._emit(
            on_event,
            "task-chosen",
            f"selected: {selected_task.name} ({task_choice_seconds:.3f}s)",
        )
        self._emit(
            on_event,
            "memory-search-hints",
            (
                f"{memory_search_hints.model_dump(mode='json')} "
                f"({memory_search_seconds:.3f}s)"
            ),
        )
        self._emit(
            on_event,
            "search-depths",
            f"{search_depths.model_dump(mode='json')} ({search_depth_seconds:.3f}s)",
        )
        await self._checkpoint(turn_control)

        (
            retrieved_memories,
            memory_retrieval_seconds,
            post_vad_memory_retrieval_seconds,
        ) = await self._maybe_retrieve_memories(
            memory_search_hints,
            search_depths,
            post_vad_started_at,
            on_event,
        )
        await self._checkpoint(turn_control)

        self._emit(
            on_event,
            "turn-continuation",
            "continuing with retrieved memories in BAML",
        )
        continuation = await self._turn_flow.continue_prompt(
            routed_transcript,
            selected_task,
            retrieved_memories or RetrievedMemoryContext(),
        )
        post_vad_completion_seconds = time.perf_counter() - post_vad_started_at
        relevance_decision = continuation.relevance_decision
        relevant_memories = BamlRetrievedMemoryContext.from_graph(
            continuation.selected_memories,
        )
        task_prompt = continuation.task_prompt
        memory_relevance_seconds = _seconds_from_ms(
            continuation.timings.memory_relevance_ms,
        )
        task_prompt_seconds = _seconds_from_ms(
            continuation.timings.task_prompt_ms,
        )
        self._emit(
            on_event,
            "memory-relevance-decision",
            (
                f"{relevance_decision.model_dump(mode='json')} "
                f"({memory_relevance_seconds:.3f}s)"
            ),
        )
        self._emit(
            on_event,
            "task-prompt-generated",
            (
                f"{len(task_prompt.full_task_prompt)} chars "
                f"({task_prompt_seconds:.3f}s)"
            ),
        )
        await self._checkpoint(turn_control)

        (
            task_execution,
            task_execution_seconds,
            post_vad_task_execution_seconds,
        ) = await self._maybe_execute_task(
            task_choice,
            task_prompt,
            post_vad_started_at,
            on_event,
        )
        await self._checkpoint(turn_control)
        (
            primitive_dispatch,
            primitive_dispatch_seconds,
            post_vad_primitive_dispatch_seconds,
        ) = await self._maybe_dispatch_primitives(
            task_execution,
            post_vad_started_at,
            on_event,
        )
        await self._checkpoint(turn_control)
        (
            action_history_summary,
            action_history_summary_seconds,
            post_vad_action_history_summary_seconds,
        ) = await self._maybe_summarize_action_history(
            primitive_dispatch,
            task_choice,
            post_vad_started_at,
            on_event,
        )
        await self._checkpoint(turn_control)
        (
            task_completion,
            task_completion_seconds,
            post_vad_task_completion_seconds,
        ) = await self._maybe_check_task_completion(
            selected_task,
            action_history_summary,
            post_vad_started_at,
            on_event,
        )
        await self._checkpoint(turn_control)
        post_vad_transcript_seconds = time.perf_counter() - post_vad_started_at
        return transcribed_turn_result(
            config=self._config,
            conversation_mode=conversation_mode,
            capture=capture,
            transcript=transcript,
            trigger_detection=trigger_detection,
            routed_transcript=routed_transcript,
            task_choice=task_choice,
            memory_search_hints=memory_search_hints,
            search_depths=search_depths,
            retrieved_memories=retrieved_memories,
            relevance_decision=relevance_decision,
            relevant_memories=relevant_memories,
            selected_memory_contexts=continuation.selected_memory_contexts,
            task_prompt=task_prompt,
            task_execution=task_execution,
            primitive_dispatch=primitive_dispatch,
            action_history_summary=action_history_summary,
            task_completion=task_completion,
            timings={
                "model_prepare_seconds": model_prepare_seconds,
                "total_started_at": total_started_at,
                "post_vad_transcript_seconds": post_vad_transcript_seconds,
                "post_vad_task_choice_seconds": post_vad_understanding_seconds,
                "post_vad_memory_search_seconds": post_vad_understanding_seconds,
                "post_vad_search_depth_seconds": post_vad_understanding_seconds,
                "post_vad_memory_retrieval_seconds": (
                    post_vad_memory_retrieval_seconds
                ),
                "post_vad_memory_relevance_seconds": post_vad_completion_seconds,
                "post_vad_task_prompt_seconds": post_vad_completion_seconds,
                "post_vad_task_execution_seconds": (
                    post_vad_task_execution_seconds
                ),
                "post_vad_primitive_dispatch_seconds": (
                    post_vad_primitive_dispatch_seconds
                ),
                "post_vad_action_history_summary_seconds": (
                    post_vad_action_history_summary_seconds
                ),
                "post_vad_task_completion_seconds": (
                    post_vad_task_completion_seconds
                ),
                "transcription_seconds": transcription_seconds,
                "task_choice_seconds": task_choice_seconds,
                "memory_search_seconds": memory_search_seconds,
                "search_depth_seconds": search_depth_seconds,
                "memory_retrieval_seconds": memory_retrieval_seconds,
                "memory_relevance_seconds": memory_relevance_seconds,
                "task_prompt_seconds": task_prompt_seconds,
                "task_execution_seconds": task_execution_seconds,
                "primitive_dispatch_seconds": primitive_dispatch_seconds,
                "action_history_summary_seconds": action_history_summary_seconds,
                "task_completion_seconds": task_completion_seconds,
            },
        )

    async def _process_conversation_on_confirmation(
        self,
        *,
        capture: CaptureResult,
        conversation_mode: baml_context.ConversationMode,
        model_prepare_seconds: float,
        total_started_at: float,
        on_event: VoicePipelineEventHandler | None,
        turn_control: VoiceTurnControl | None,
    ) -> VoiceTurnResult:
        assert capture.utterance is not None
        assert capture.keyphrase_detection is not None

        utterance = capture.utterance
        await self._wait_for_speculative_transcription_start(turn_control)
        self._emit(
            on_event,
            "transcribing",
            (
                f"{utterance.duration_seconds:.2f}s conversation-mode "
                f"confirmation with {_transcriber_label(self._transcriber)}"
            ),
        )
        transcription_started_at = time.perf_counter()
        transcript = await run_in_daemon_thread(
            transcribe_with_initial_prompt,
            self._transcriber,
            utterance.samples,
            utterance.sample_rate,
            CONVERSATION_ON_CONFIRMATION_PROMPT,
        )
        transcription_seconds = time.perf_counter() - transcription_started_at
        await self._checkpoint(turn_control)
        self._emit(
            on_event,
            "transcript",
            f"{transcript.text or '<empty>'} ({transcription_seconds:.3f}s)",
        )

        trigger_detection = self._trigger_matcher.match_confirmed(
            transcript.text,
            "conversation_on",
            capture.keyphrase_detection.phrase,
        )
        await self._wait_until_committed(turn_control)
        if _is_conversation_on_trigger_only(trigger_detection):
            mode = self._turn_on_conversation_mode(on_event)
            return mode_switch_turn_result(
                _mode_switch_capture(capture, mode),
                mode,
                model_prepare_seconds,
                total_started_at,
            )

        self._emit(
            on_event,
            "turn-ignored",
            (
                "conversation-mode confirmation rejected "
                f"heard={transcript.text or '<empty>'!r}"
            ),
        )
        return ignored_turn_result(
            self._config,
            capture,
            conversation_mode,
            model_prepare_seconds,
            total_started_at,
        )

    def _turn_on_conversation_mode(
        self,
        on_event: VoicePipelineEventHandler | None,
    ) -> baml_context.ConversationMode:
        mode = baml_context.ConversationMode.CONTINUOUS_CONVERSATION
        changed = True
        if self._mode_controller is not None:
            changed = self._mode_controller.set(mode)
        if changed:
            self._emit(on_event, "conversation-mode", mode.value)
        return mode

    def _remember_live_human_reply(self, routed_transcript: str) -> None:
        if self._live_conversation is None:
            return
        self._live_conversation.add_message(
            self._config.conversation_id,
            role="human",
            content=routed_transcript,
        )

    def _record_human_reply_in_background(
        self,
        routed_transcript: str,
        on_event: VoicePipelineEventHandler | None,
    ) -> None:
        if self._config.conversation_id is None or not routed_transcript:
            return

        def record() -> None:
            try:
                asyncio.run(self._record_human_reply(routed_transcript, on_event))
            except Exception as exc:
                self._emit(
                    on_event,
                    "warning",
                    f"failed to record human reply: {exc}",
                )

        Thread(target=record, daemon=True).start()

    async def _record_human_reply(
        self,
        routed_transcript: str,
        on_event: VoicePipelineEventHandler | None,
    ) -> None:
        if self._config.conversation_id is None or not routed_transcript:
            return

        database = await open_memory_database()
        try:
            await database.conversations.add_message(
                self._config.conversation_id,
                ConversationMessage(
                    role="human",
                    content=routed_transcript,
                ),
            )
        finally:
            await database.close()

        self._emit(
            on_event,
            "conversation-context",
            f"recorded current turn in {self._config.conversation_id}",
        )

    async def _maybe_retrieve_memories(
        self,
        memory_search_hints: baml_memory_search.ConversationMemorySearchHints | None,
        search_depths: baml_memory_search.SearchDepthDecision | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ) -> tuple[RetrievedMemoryContext | None, float | None, float | None]:
        if not self._config.task_choice_enabled:
            return None, None, None
        if memory_search_hints is None or search_depths is None:
            return None, None, None

        self._emit(
            on_event,
            "memory-retrieval",
            "retrieving graph memory context",
        )
        memory_retrieval_started_at = time.perf_counter()
        retrieved = await self._memory_retrieval.retrieve(
            memory_search_hints=memory_search_hints,
            search_depths=search_depths,
        )
        memory_retrieval_seconds = time.perf_counter() - memory_retrieval_started_at
        self._emit(
            on_event,
            "memory-retrieved",
            f"{retrieved.to_dict()} ({memory_retrieval_seconds:.3f}s)",
        )
        return (
            retrieved,
            memory_retrieval_seconds,
            time.perf_counter() - post_vad_started_at,
        )

    async def _maybe_execute_task(
        self,
        task_choice: baml_task_routing.TaskChoiceDecision | None,
        task_prompt: baml_task_prompt.TaskPromptDecision | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ) -> tuple[baml_task_execution.TaskExecutionResult | None, float | None, float | None]:
        if not self._config.task_choice_enabled:
            return None, None, None
        if self._task_execution is None or task_choice is None or task_prompt is None:
            return None, None, None

        self._emit(on_event, "task-execution", "executing selected task")
        started_at = time.perf_counter()
        result = await self._task_execution.execute_task(
            selected_task_id=task_choice.selected_task_id,
            full_task_prompt=task_prompt.full_task_prompt,
            prompt_layer_debug=getattr(self._turn_flow, "prompt_layer_debug", None),
        )
        seconds = time.perf_counter() - started_at
        self._emit(
            on_event,
            "task-executed",
            f"{len(result.returns)} return items ({seconds:.3f}s)",
        )
        return result, seconds, time.perf_counter() - post_vad_started_at

    async def _maybe_summarize_action_history(
        self,
        primitive_dispatch,
        task_choice: baml_task_routing.TaskChoiceDecision | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ):
        if primitive_dispatch is None or primitive_dispatch.task_history_id is None:
            return None, None, None

        self._emit(
            on_event,
            "action-history-summary",
            "summarizing recorded action history",
        )
        started_at = time.perf_counter()
        summarizer = ActionHistorySummarizer(
            session_id=self._config.session_id,
            conversation_id=self._config.conversation_id,
        )
        try:
            result = await summarizer.summarize(
                primitive_dispatch.task_history_id,
                selected_task_id=(
                    task_choice.selected_task_id if task_choice is not None else None
                ),
                prompt_layer_debug=getattr(self._turn_flow, "prompt_layer_debug", None),
            )
        finally:
            await summarizer.close()
        seconds = time.perf_counter() - started_at
        self._emit(
            on_event,
            "action-history-summarized",
            f"{len(result)} chars ({seconds:.3f}s)",
        )
        return result, seconds, time.perf_counter() - post_vad_started_at

    async def _maybe_check_task_completion(
        self,
        selected_task: baml_task_routing.SelectedTaskContext | None,
        action_history_summary: str | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ) -> tuple[baml_task_completion.CompletionResult | None, float | None, float | None]:
        if selected_task is None or action_history_summary is None:
            return None, None, None

        self._emit(
            on_event,
            "task-completion-review",
            "checking task completion",
        )
        started_at = time.perf_counter()
        result = await TaskCompletionChecker().check(
            completion_string=selected_task.output,
            output_summary=action_history_summary,
            prompt_layer_debug=getattr(self._turn_flow, "prompt_layer_debug", None),
        )
        seconds = time.perf_counter() - started_at
        self._emit(
            on_event,
            "task-completion-reviewed",
            f"{result.value} ({seconds:.3f}s)",
        )
        return result, seconds, time.perf_counter() - post_vad_started_at

    async def _maybe_dispatch_primitives(
        self,
        task_execution: baml_task_execution.TaskExecutionResult | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ):
        if task_execution is None or not task_execution.returns:
            return None, None, None

        self._emit(on_event, "primitive-dispatch", "handling task return items")
        started_at = time.perf_counter()
        database = await open_memory_database()
        try:
            result = await PrimitiveDispatcher(
                database=database,
                session_id=self._config.session_id,
                conversation_id=self._config.conversation_id,
                speaker=self._speaker,
                on_event=on_event,
                on_conversation_mode_off=(
                    self._mode_controller.turn_off_conversation
                    if self._mode_controller is not None
                    else None
                ),
            ).dispatch(task_execution)
        finally:
            await database.close()
        seconds = time.perf_counter() - started_at
        self._emit(
            on_event,
            "primitive-dispatched",
            f"{len(result.records)} items ({seconds:.3f}s)",
        )
        return result, seconds, time.perf_counter() - post_vad_started_at

    def _emit(
        self,
        on_event: VoicePipelineEventHandler | None,
        stage: str,
        message: str,
    ) -> None:
        if on_event is not None:
            on_event(stage, message)


def _is_continuous_unprompted(
    conversation_mode: baml_context.ConversationMode,
    capture: CaptureResult,
) -> bool:
    return (
        conversation_mode == baml_context.ConversationMode.CONTINUOUS_CONVERSATION
        and capture.keyphrase_detection is None
    )


def _is_conversation_on_confirmation(capture: CaptureResult) -> bool:
    return (
        capture.keyphrase_detection is not None
        and capture.keyphrase_detection.kind == "conversation_on"
        and not capture.mode_switched
    )


def _is_conversation_on_trigger_only(trigger_detection) -> bool:
    return (
        trigger_detection is not None
        and trigger_detection.kind == "conversation_on"
        and not trigger_detection.routed_transcript
    )


def _mode_switch_capture(
    capture: CaptureResult,
    mode: baml_context.ConversationMode,
) -> CaptureResult:
    return CaptureResult(
        conversation_mode=mode,
        keyphrase_detection=capture.keyphrase_detection,
        utterance=None,
        mode_switched=True,
        keyphrase_wait_seconds=capture.keyphrase_wait_seconds,
        listen_seconds=capture.listen_seconds,
        wait_for_speech_seconds=None,
        speech_capture_wall_seconds=None,
    )


def _transcriber_label(transcriber: Transcriber) -> str:
    return str(getattr(transcriber, "label", "configured transcriber"))


def _seconds_from_ms(milliseconds) -> float:
    return float(milliseconds) / 1000.0
