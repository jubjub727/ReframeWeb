from __future__ import annotations

import time

from baml_sdk import turn_context as baml_turn_context
from reframe_agent_host.agent_flow.live_conversation import LiveConversationContext
from reframe_agent_host.agent_flow.task_execution import TaskExecutionPlanner
from reframe_agent_host.speech.transcription import (
    CONVERSATION_ON_CONFIRMATION_PROMPT,
    Transcriber,
    transcribe_with_initial_prompt,
)
from reframe_agent_host.speech.triggers import TriggerPhraseMatcher
from reframe_agent_host.speech.tts import NoopSpeaker, TextSpeaker
from reframe_agent_host.voice.agent_turn import process_agent_turn
from reframe_agent_host.voice.conversation_mode import ConversationModeController
from reframe_agent_host.voice.daemon_threads import run_in_daemon_thread
from reframe_agent_host.voice.turn_results import (
    ignored_turn_result,
    mode_switch_turn_result,
)
from reframe_agent_host.voice.turn_side_effects import TurnSideEffects
from reframe_agent_host.voice.capture_types import CaptureResult, VoiceTurnControl
from reframe_agent_host.voice.pipeline_config import (
    VoicePipelineConfig,
    VoicePipelineEventHandler,
)
from reframe_agent_host.voice.turn_data import VoiceTurnResult
from reframe_agent_host.voice.utterance_quality import (
    should_ignore_continuous_utterance,
)


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
        self._mode_controller = mode_controller
        self._turn_flow = turn_flow
        self._side_effects = TurnSideEffects(
            config=config,
            memory_retrieval=memory_retrieval,
            task_execution=task_execution,
            speaker=speaker or NoopSpeaker(),
            mode_controller=mode_controller,
            turn_flow=turn_flow,
            live_conversation=live_conversation,
        )

    async def process(
        self,
        capture: CaptureResult,
        conversation_mode: baml_turn_context.ConversationMode,
        model_prepare_seconds: float,
        total_started_at: float,
        on_event: VoicePipelineEventHandler | None,
        turn_control: VoiceTurnControl | None = None,
    ) -> VoiceTurnResult:
        if capture.mode_switched and capture.utterance is None:
            return mode_switch_turn_result(
                capture, conversation_mode, model_prepare_seconds, total_started_at
            )
        if capture.utterance is None:
            raise RuntimeError("Capture finished without an utterance.")

        post_vad_started_at = time.perf_counter()
        if _is_continuous_unprompted(conversation_mode, capture):
            ignored, quality = should_ignore_continuous_utterance(
                capture.utterance.samples,
                capture.utterance.sample_rate,
            )
            if ignored:
                await _wait_until_committed(turn_control)
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

        await _wait_for_speculative_transcription_start(turn_control)
        transcript, transcription_seconds = await self._transcribe(
            capture, on_event, turn_control
        )
        trigger_detection = self._match_trigger(transcript.text, capture)
        routed_transcript = (
            trigger_detection.routed_transcript
            if trigger_detection is not None
            else transcript.text
        )
        if _is_conversation_on_trigger_only(trigger_detection):
            await _wait_until_committed(turn_control)
            mode = self._turn_on_conversation_mode(on_event)
            return mode_switch_turn_result(
                _mode_switch_capture(capture, mode),
                mode,
                model_prepare_seconds,
                total_started_at,
            )

        await _wait_until_committed(turn_control)
        human_reply_created_at = None
        if routed_transcript:
            human_reply_created_at = self._side_effects.remember_live_human_reply(
                routed_transcript
            )
            bind_human_reply = getattr(self._turn_flow, "bind_human_reply", None)
            if bind_human_reply is not None:
                bind_human_reply(human_reply_created_at)
            self._emit(on_event, "human-reply", routed_transcript)
            self._side_effects.record_human_reply_in_background(
                routed_transcript, on_event
            )
        if trigger_detection is not None:
            self._emit(
                on_event,
                "trigger",
                f"{trigger_detection.kind} {trigger_detection.phrase!r}",
            )

        result = await process_agent_turn(
            config=self._config,
            turn_flow=self._turn_flow,
            side_effects=self._side_effects,
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
        self._side_effects.resolve_live_human_reply(human_reply_created_at)
        return result

    async def _transcribe(self, capture, on_event, turn_control):
        utterance = capture.utterance
        self._emit(
            on_event,
            "transcribing",
            f"{utterance.duration_seconds:.2f}s utterance with {_transcriber_label(self._transcriber)}",
        )
        started_at = time.perf_counter()
        transcript = await run_in_daemon_thread(
            self._transcriber.transcribe,
            utterance.samples,
            utterance.sample_rate,
        )
        elapsed = time.perf_counter() - started_at
        await _checkpoint(turn_control)
        self._emit(
            on_event,
            "transcript",
            f"{transcript.text or '<empty>'} ({elapsed:.3f}s)",
        )
        return transcript, elapsed

    async def _process_conversation_on_confirmation(
        self,
        *,
        capture: CaptureResult,
        conversation_mode: baml_turn_context.ConversationMode,
        model_prepare_seconds: float,
        total_started_at: float,
        on_event: VoicePipelineEventHandler | None,
        turn_control: VoiceTurnControl | None,
    ) -> VoiceTurnResult:
        assert capture.utterance is not None
        assert capture.keyphrase_detection is not None
        await _wait_for_speculative_transcription_start(turn_control)
        self._emit(
            on_event,
            "transcribing",
            (
                f"{capture.utterance.duration_seconds:.2f}s conversation-mode "
                f"confirmation with {_transcriber_label(self._transcriber)}"
            ),
        )
        started_at = time.perf_counter()
        transcript = await run_in_daemon_thread(
            transcribe_with_initial_prompt,
            self._transcriber,
            capture.utterance.samples,
            capture.utterance.sample_rate,
            CONVERSATION_ON_CONFIRMATION_PROMPT,
        )
        transcription_seconds = time.perf_counter() - started_at
        await _checkpoint(turn_control)
        self._emit(
            on_event,
            "transcript",
            f"{transcript.text or '<empty>'} ({transcription_seconds:.3f}s)",
        )
        trigger = self._trigger_matcher.match_confirmed(
            transcript.text,
            "conversation_on",
            capture.keyphrase_detection.phrase,
        )
        await _wait_until_committed(turn_control)
        if _is_conversation_on_trigger_only(trigger):
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
            f"conversation-mode confirmation rejected heard={transcript.text or '<empty>'!r}",
        )
        return ignored_turn_result(
            self._config,
            capture,
            conversation_mode,
            model_prepare_seconds,
            total_started_at,
        )

    def _match_trigger(self, transcript: str, capture: CaptureResult):
        if capture.keyphrase_detection is None:
            return self._trigger_matcher.match(transcript)
        return self._trigger_matcher.match_confirmed(
            transcript,
            capture.keyphrase_detection.kind,
            capture.keyphrase_detection.phrase,
        )

    def _turn_on_conversation_mode(self, on_event):
        mode = baml_turn_context.ConversationMode.CONTINUOUS_CONVERSATION
        changed = self._mode_controller is None or self._mode_controller.set(mode)
        if changed:
            self._emit(on_event, "conversation-mode", mode.value)
        return mode

    async def close(self) -> None:
        await self._side_effects.close()

    @staticmethod
    def _emit(on_event, stage: str, message: str) -> None:
        if on_event is not None:
            on_event(stage, message)


async def _checkpoint(turn_control: VoiceTurnControl | None) -> None:
    if turn_control is not None:
        await turn_control.checkpoint()


async def _wait_until_committed(turn_control: VoiceTurnControl | None) -> None:
    if turn_control is not None:
        await turn_control.wait_until_committed()


async def _wait_for_speculative_transcription_start(
    turn_control: VoiceTurnControl | None,
) -> None:
    if turn_control is not None:
        await turn_control.wait_for_commit_or_cancel(
            SPECULATIVE_TRANSCRIPTION_GRACE_SECONDS
        )


def _is_continuous_unprompted(mode, capture: CaptureResult) -> bool:
    return (
        mode == baml_turn_context.ConversationMode.CONTINUOUS_CONVERSATION
        and capture.keyphrase_detection is None
    )


def _is_conversation_on_confirmation(capture: CaptureResult) -> bool:
    return (
        capture.keyphrase_detection is not None
        and capture.keyphrase_detection.kind == "conversation_on"
        and not capture.mode_switched
    )


def _is_conversation_on_trigger_only(trigger) -> bool:
    return (
        trigger is not None
        and trigger.kind == "conversation_on"
        and not trigger.routed_transcript
    )


def _mode_switch_capture(capture: CaptureResult, mode) -> CaptureResult:
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
