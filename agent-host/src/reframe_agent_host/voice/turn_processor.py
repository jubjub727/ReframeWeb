from __future__ import annotations

import time

from reframe_agent_host.agent_flow.planning import ConversationPlanner
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
        planner: ConversationPlanner,
    ) -> None:
        self._config = config
        self._transcriber = transcriber
        self._trigger_matcher = trigger_matcher
        self._planner = planner

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

        plan, planning_seconds, post_vad_plan_seconds = await self._maybe_plan(
            routed_transcript,
            conversation_mode,
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
            plan=plan,
            timings={
                "model_prepare_seconds": model_prepare_seconds,
                "total_started_at": total_started_at,
                "post_vad_transcript_seconds": post_vad_transcript_seconds,
                "post_vad_plan_seconds": post_vad_plan_seconds,
                "transcription_seconds": transcription_seconds,
                "planning_seconds": planning_seconds,
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

    async def _maybe_plan(
        self,
        routed_transcript: str,
        conversation_mode: types.ConversationMode,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ):
        if not self._config.plan_enabled:
            return None, None, None
        if not routed_transcript:
            self._emit(on_event, "planning", "skipped empty transcript")
            return None, None, None

        self._emit(on_event, "planning", "sending transcript to BAML")
        planning_started_at = time.perf_counter()
        plan = await self._planner.plan(
            transcript=routed_transcript,
            conversation_mode=conversation_mode,
            playback_state=self._config.playback_state,
        )
        planning_seconds = time.perf_counter() - planning_started_at
        self._emit(on_event, "planned", f"{plan.interpreted_intent} ({planning_seconds:.3f}s)")
        return plan, planning_seconds, time.perf_counter() - post_vad_started_at

    def _emit(
        self,
        on_event: VoicePipelineEventHandler | None,
        stage: str,
        message: str,
    ) -> None:
        if on_event is not None:
            on_event(stage, message)
