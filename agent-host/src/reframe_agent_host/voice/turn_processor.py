from __future__ import annotations

import time

from reframe_agent_host.agent_flow.conversation_evaluation import (
    ConversationEvaluationPlanner,
)
from reframe_agent_host.agent_flow.task_choice import TaskChoicePlanner
from reframe_agent_host.baml_client import types
from reframe_agent_host.speech.transcription import FasterWhisperTranscriber
from reframe_agent_host.speech.triggers import TriggerPhraseMatcher
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


class VoiceTurnProcessor:
    def __init__(
        self,
        config: VoicePipelineConfig,
        transcriber: FasterWhisperTranscriber,
        trigger_matcher: TriggerPhraseMatcher,
        planner: TaskChoicePlanner,
        conversation_evaluation: ConversationEvaluationPlanner,
    ) -> None:
        self._config = config
        self._transcriber = transcriber
        self._trigger_matcher = trigger_matcher
        self._planner = planner
        self._conversation_evaluation = conversation_evaluation

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
            timings={
                "model_prepare_seconds": model_prepare_seconds,
                "total_started_at": total_started_at,
                "post_vad_transcript_seconds": post_vad_transcript_seconds,
                "post_vad_task_choice_seconds": post_vad_task_choice_seconds,
                "post_vad_memory_search_seconds": post_vad_memory_search_seconds,
                "transcription_seconds": transcription_seconds,
                "task_choice_seconds": task_choice_seconds,
                "memory_search_seconds": memory_search_seconds,
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
        return (
            task_choice,
            task_choice_seconds,
            time.perf_counter() - post_vad_started_at,
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

    def _emit(
        self,
        on_event: VoicePipelineEventHandler | None,
        stage: str,
        message: str,
    ) -> None:
        if on_event is not None:
            on_event(stage, message)
