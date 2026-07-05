from __future__ import annotations

import time

from reframe_agent_host.agent_flow.relevance_candidates import (
    filter_retrieved_memories,
)
from reframe_agent_host.agent_flow.conversation_evaluation import (
    ConversationEvaluationPlanner,
)
from reframe_agent_host.agent_flow.search_depth import SearchDepthPlanner
from reframe_agent_host.agent_flow.task_choice import TaskChoicePlanner
from reframe_agent_host.agent_flow.task_execution import TaskExecutionPlanner
from reframe_agent_host.baml_client import types
from reframe_agent_host.speech.transcription import FasterWhisperTranscriber
from reframe_agent_host.speech.triggers import TriggerPhraseMatcher
from reframe_agent_host.speech.tts import NoopSpeaker, TextSpeaker
from reframe_agent_host.task_execution import PrimitiveDispatcher
from reframe_agent_host.voice.turn_results import (
    mode_switch_turn_result,
    transcribed_turn_result,
)
from reframe_agent_host.voice.types import (
    CaptureResult,
    VoicePipelineConfig,
    VoicePipelineEventHandler,
    VoiceTurnResult,
)
from reframe_memory import ConversationMessage, open_memory_database
from reframe_memory.retrieved_context import RetrievedMemoryContext


class VoiceTurnProcessor:
    def __init__(
        self,
        config: VoicePipelineConfig,
        transcriber: FasterWhisperTranscriber,
        trigger_matcher: TriggerPhraseMatcher,
        planner: TaskChoicePlanner,
        conversation_evaluation: ConversationEvaluationPlanner,
        search_depth: SearchDepthPlanner,
        memory_retrieval,
        memory_relevance,
        task_prompt,
        task_execution: TaskExecutionPlanner | None = None,
        speaker: TextSpeaker | None = None,
    ) -> None:
        self._config = config
        self._transcriber = transcriber
        self._trigger_matcher = trigger_matcher
        self._planner = planner
        self._conversation_evaluation = conversation_evaluation
        self._search_depth = search_depth
        self._memory_retrieval = memory_retrieval
        self._memory_relevance = memory_relevance
        self._task_prompt = task_prompt
        self._task_execution = task_execution
        self._speaker = speaker or NoopSpeaker()

    async def process(
        self,
        capture: CaptureResult,
        conversation_mode: types.ConversationMode,
        model_prepare_seconds: float,
        total_started_at: float,
        on_event: VoicePipelineEventHandler | None,
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
        self._emit(
            on_event,
            "transcribing",
            f"{utterance.duration_seconds:.2f}s utterance with faster-whisper",
        )
        transcription_started_at = time.perf_counter()
        transcript = self._transcriber.transcribe(
            utterance.samples,
            utterance.sample_rate,
        )
        transcription_seconds = time.perf_counter() - transcription_started_at
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
        if routed_transcript:
            self._emit(on_event, "human-reply", routed_transcript)
        if trigger_detection is not None:
            self._emit(
                on_event,
                "trigger",
                f"{trigger_detection.kind} {trigger_detection.phrase!r}",
            )

        task_choice, task_choice_seconds, post_vad_task_choice_seconds = (
            await self._maybe_choose_task(
                routed_transcript,
                post_vad_started_at,
                on_event,
            )
        )
        await self._record_current_turn_context(
            routed_transcript,
            task_choice,
            on_event,
        )
        (
            memory_search_hints,
            memory_search_seconds,
            post_vad_memory_search_seconds,
        ) = await self._maybe_evaluate_memory_search(
            routed_transcript,
            task_choice,
            post_vad_started_at,
            on_event,
        )
        (
            search_depths,
            search_depth_seconds,
            post_vad_search_depth_seconds,
        ) = await self._maybe_evaluate_search_depths(
            routed_transcript,
            task_choice,
            memory_search_hints,
            post_vad_started_at,
            on_event,
        )
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
        (
            relevance_decision,
            relevant_memories,
            memory_relevance_seconds,
            post_vad_memory_relevance_seconds,
        ) = await self._maybe_evaluate_memory_relevance(
            routed_transcript,
            task_choice,
            retrieved_memories,
            post_vad_started_at,
            on_event,
        )
        (
            task_prompt,
            task_prompt_seconds,
            post_vad_task_prompt_seconds,
        ) = await self._maybe_generate_task_prompt(
            routed_transcript,
            task_choice,
            relevance_decision,
            relevant_memories,
            post_vad_started_at,
            on_event,
        )
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
        (
            primitive_dispatch,
            primitive_dispatch_seconds,
            post_vad_primitive_dispatch_seconds,
        ) = await self._maybe_dispatch_primitives(
            task_execution,
            post_vad_started_at,
            on_event,
        )
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
            task_prompt=task_prompt,
            task_execution=task_execution,
            primitive_dispatch=primitive_dispatch,
            timings={
                "model_prepare_seconds": model_prepare_seconds,
                "total_started_at": total_started_at,
                "post_vad_transcript_seconds": post_vad_transcript_seconds,
                "post_vad_task_choice_seconds": post_vad_task_choice_seconds,
                "post_vad_memory_search_seconds": post_vad_memory_search_seconds,
                "post_vad_search_depth_seconds": post_vad_search_depth_seconds,
                "post_vad_memory_retrieval_seconds": (
                    post_vad_memory_retrieval_seconds
                ),
                "post_vad_memory_relevance_seconds": (
                    post_vad_memory_relevance_seconds
                ),
                "post_vad_task_prompt_seconds": post_vad_task_prompt_seconds,
                "post_vad_task_execution_seconds": (
                    post_vad_task_execution_seconds
                ),
                "post_vad_primitive_dispatch_seconds": (
                    post_vad_primitive_dispatch_seconds
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
            },
        )

    def _match_trigger(self, transcript: str, capture: CaptureResult):
        if capture.keyphrase_detection is None:
            return self._trigger_matcher.match(transcript)
        return self._trigger_matcher.match_confirmed(
            transcript,
            capture.keyphrase_detection.kind,
            capture.keyphrase_detection.phrase,
        )

    async def _maybe_choose_task(
        self,
        routed_transcript: str,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ):
        if not self._config.task_choice_enabled:
            return None, None, None
        if not routed_transcript:
            self._emit(on_event, "task-choice", "skipped empty transcript")
            return None, None, None

        self._emit(on_event, "task-choice", "choosing initial task with BAML")
        task_choice_started_at = time.perf_counter()
        task_choice = await self._planner.choose_initial_task(
            current_user_request=routed_transcript,
        )
        task_choice_seconds = time.perf_counter() - task_choice_started_at
        self._emit(
            on_event,
            "task-chosen",
            f"{task_choice.selected_task_id} ({task_choice_seconds:.3f}s)",
        )
        if task_choice.agent_thought:
            self._emit(on_event, "agent-thought", task_choice.agent_thought)
        return (
            task_choice,
            task_choice_seconds,
            time.perf_counter() - post_vad_started_at,
        )

    async def _record_current_turn_context(
        self,
        routed_transcript: str,
        task_choice: types.TaskChoiceDecision | None,
        on_event: VoicePipelineEventHandler | None,
    ) -> None:
        if self._config.conversation_id is None or not routed_transcript:
            return

        database = await open_memory_database()
        try:
            await database.apply_schema()
            await database.ensure_roots()
            await database.conversations.add_message(
                self._config.conversation_id,
                ConversationMessage(
                    role="human",
                    content=routed_transcript,
                ),
            )
            thought = (task_choice.agent_thought or "").strip() if task_choice else ""
            if thought:
                await database.conversations.add_message(
                    self._config.conversation_id,
                    ConversationMessage(
                        role="agent_thought",
                        content=thought,
                    ),
                )
        finally:
            await database.close()

        self._emit(
            on_event,
            "conversation-context",
            f"recorded current turn in {self._config.conversation_id}",
        )

    async def _maybe_evaluate_memory_search(
        self,
        routed_transcript: str,
        task_choice: types.TaskChoiceDecision | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ):
        if not self._config.task_choice_enabled:
            return None, None, None
        if task_choice is None or not routed_transcript:
            return None, None, None

        self._emit(
            on_event,
            "memory-search",
            "evaluating conversation memory search hints with BAML",
        )
        memory_search_started_at = time.perf_counter()
        hints = await self._conversation_evaluation.evaluate_for_memory_search(
            current_user_request=routed_transcript,
            selected_task_id=task_choice.selected_task_id,
        )
        memory_search_seconds = time.perf_counter() - memory_search_started_at
        self._emit(
            on_event,
            "memory-search-hints",
            f"{hints.model_dump(mode='json')} ({memory_search_seconds:.3f}s)",
        )
        return (
            hints,
            memory_search_seconds,
            time.perf_counter() - post_vad_started_at,
        )

    async def _maybe_evaluate_search_depths(
        self,
        routed_transcript: str,
        task_choice: types.TaskChoiceDecision | None,
        memory_search_hints: types.ConversationMemorySearchHints | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ):
        if not self._config.task_choice_enabled:
            return None, None, None
        if task_choice is None or memory_search_hints is None or not routed_transcript:
            return None, None, None

        self._emit(
            on_event,
            "search-depth",
            "evaluating historic memory search depth with BAML",
        )
        search_depth_started_at = time.perf_counter()
        depths = await self._search_depth.evaluate_search_depths(
            current_user_request=routed_transcript,
            selected_task_id=task_choice.selected_task_id,
            memory_search_hints=memory_search_hints,
        )
        search_depth_seconds = time.perf_counter() - search_depth_started_at
        self._emit(
            on_event,
            "search-depths",
            f"{depths.model_dump(mode='json')} ({search_depth_seconds:.3f}s)",
        )
        return (
            depths,
            search_depth_seconds,
            time.perf_counter() - post_vad_started_at,
        )

    async def _maybe_retrieve_memories(
        self,
        memory_search_hints: types.ConversationMemorySearchHints | None,
        search_depths: types.SearchDepthDecision | None,
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

    async def _maybe_evaluate_memory_relevance(
        self,
        routed_transcript: str,
        task_choice: types.TaskChoiceDecision | None,
        retrieved_memories: RetrievedMemoryContext | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ) -> tuple[
        types.RelevantMemoryDecision | None,
        RetrievedMemoryContext | None,
        float | None,
        float | None,
    ]:
        if not self._config.task_choice_enabled:
            return None, None, None, None
        if task_choice is None or retrieved_memories is None or not routed_transcript:
            return None, None, None, None

        self._emit(
            on_event,
            "memory-relevance",
            "filtering retrieved memories with BAML",
        )
        memory_relevance_started_at = time.perf_counter()
        decision = await self._memory_relevance.evaluate_relevant_memories(
            current_user_request=routed_transcript,
            selected_task_id=task_choice.selected_task_id,
            retrieved_memories=retrieved_memories,
        )
        relevant_memories = filter_retrieved_memories(retrieved_memories, decision)
        memory_relevance_seconds = time.perf_counter() - memory_relevance_started_at
        self._emit(
            on_event,
            "memory-relevance-decision",
            f"{decision.model_dump(mode='json')} ({memory_relevance_seconds:.3f}s)",
        )
        return (
            decision,
            relevant_memories,
            memory_relevance_seconds,
            time.perf_counter() - post_vad_started_at,
        )

    async def _maybe_generate_task_prompt(
        self,
        routed_transcript: str,
        task_choice: types.TaskChoiceDecision | None,
        relevance_decision: types.RelevantMemoryDecision | None,
        relevant_memories: RetrievedMemoryContext | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ) -> tuple[types.TaskPromptDecision | None, float | None, float | None]:
        if not self._config.task_choice_enabled:
            return None, None, None
        if task_choice is None or relevant_memories is None or not routed_transcript:
            return None, None, None

        self._emit(
            on_event,
            "task-prompt",
            "generating final task prompt with BAML",
        )
        task_prompt_started_at = time.perf_counter()
        decision = await self._task_prompt.generate_task_prompt(
            current_user_request=routed_transcript,
            selected_task_id=task_choice.selected_task_id,
            selected_memories=relevant_memories,
            selected_memory_ids=(
                relevance_decision.kept_memory_ids if relevance_decision else ()
            ),
        )
        task_prompt_seconds = time.perf_counter() - task_prompt_started_at
        self._emit(
            on_event,
            "task-prompt-generated",
            f"{len(decision.full_task_prompt)} chars ({task_prompt_seconds:.3f}s)",
        )
        return (
            decision,
            task_prompt_seconds,
            time.perf_counter() - post_vad_started_at,
        )

    async def _maybe_execute_task(
        self,
        task_choice: types.TaskChoiceDecision | None,
        task_prompt: types.TaskPromptDecision | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ) -> tuple[types.TaskExecutionResult | None, float | None, float | None]:
        if not self._config.task_choice_enabled:
            return None, None, None
        if self._task_execution is None or task_choice is None or task_prompt is None:
            return None, None, None

        self._emit(on_event, "task-execution", "executing selected task")
        started_at = time.perf_counter()
        result = await self._task_execution.execute_task(
            selected_task_id=task_choice.selected_task_id,
            full_task_prompt=task_prompt.full_task_prompt,
        )
        seconds = time.perf_counter() - started_at
        self._emit(
            on_event,
            "task-executed",
            f"{len(result.returns)} return items ({seconds:.3f}s)",
        )
        return result, seconds, time.perf_counter() - post_vad_started_at

    async def _maybe_dispatch_primitives(
        self,
        task_execution: types.TaskExecutionResult | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ):
        if task_execution is None:
            return None, None, None

        self._emit(on_event, "primitive-dispatch", "handling task return items")
        started_at = time.perf_counter()
        database = await open_memory_database()
        try:
            await database.apply_schema()
            await database.ensure_roots()
            result = await PrimitiveDispatcher(
                database=database,
                session_id=self._config.session_id,
                conversation_id=self._config.conversation_id,
                speaker=self._speaker,
                on_event=on_event,
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
