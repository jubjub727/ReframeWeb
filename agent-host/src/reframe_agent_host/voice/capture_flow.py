from __future__ import annotations

import time

import numpy as np

from reframe_agent_host.voice.microphone import MicrophoneStream
import baml_sdk as types
from reframe_agent_host.voice.activity import DetectedUtterance, UtteranceSegmenter
from reframe_agent_host.voice.vad_types import UtteranceEvent
from reframe_agent_host.voice.capture_results import (
    finish_mode_switch_result,
    finish_with_utterance_result,
)
from reframe_agent_host.voice.capture_state import CaptureState
from reframe_agent_host.voice.keyphrase_gate import KeyphraseGateResult
from reframe_agent_host.voice.types import (
    CaptureResult,
    VoicePipelineConfig,
    VoicePipelineEventHandler,
)


class VoiceCaptureFlow:
    def __init__(self, config: VoicePipelineConfig) -> None:
        self._config = config

    def enable_conversation_mode(
        self,
        result: KeyphraseGateResult,
        state: CaptureState,
        segmenter: UtteranceSegmenter,
        microphone: MicrophoneStream,
        listen_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ) -> CaptureResult | None:
        state.conversation_mode = types.ConversationMode.CONTINUOUS_CONVERSATION
        state.keyphrase_required = False
        state.mode_switched = True
        state.keyphrase_carry_frames.clear()
        state.post_activation_deadline = time.perf_counter() + (
            self._config.post_activation_command_window_ms / 1000
        )
        self._emit(on_event, "keyphrase", "conversation mode enabled")

        if not result.replay_frames:
            return None

        self._emit(
            on_event,
            "keyphrase",
            f"replaying {self._duration(result.replay_frames):.2f}s after trigger to VAD",
        )
        for replay_frame in result.replay_frames:
            utterance = self.accept_speech_frame(
                replay_frame,
                segmenter,
                state,
                on_event,
            )
            if utterance is not None:
                return self.finish_with_utterance(
                    state,
                    utterance,
                    microphone,
                    listen_started_at,
                    on_event,
                )
        return None

    def replay_wake_audio(
        self,
        result: KeyphraseGateResult,
        segmenter: UtteranceSegmenter,
        state: CaptureState,
        on_event: VoicePipelineEventHandler | None,
    ) -> DetectedUtterance | None:
        frames = result.replay_frames
        if not frames:
            self._emit(on_event, "keyphrase", "no post-trigger audio to replay to VAD")
            state.keyphrase_carry_frames.clear()
            return None
        self._emit(
            on_event,
            "keyphrase",
            f"replaying {self._duration(frames):.2f}s around trigger to VAD",
        )

        for carried_frame in frames:
            utterance = self.accept_speech_frame(carried_frame, segmenter, state, on_event)
            if utterance is not None:
                state.keyphrase_carry_frames.clear()
                return utterance
        state.keyphrase_carry_frames.clear()
        return None

    def accept_speech_frame(
        self,
        frame: np.ndarray,
        segmenter: UtteranceSegmenter,
        state: CaptureState,
        on_event: VoicePipelineEventHandler | None,
    ) -> DetectedUtterance | None:
        utterance = segmenter.accept(frame)
        if segmenter.is_recording and not state.was_recording:
            state.speech_started_at = time.perf_counter()
            state.post_activation_deadline = None
            self._emit(on_event, "speech", "started")
        state.was_recording = segmenter.is_recording
        return utterance

    def accept_speech_event(
        self,
        frame: np.ndarray,
        segmenter: UtteranceSegmenter,
        state: CaptureState,
        on_event: VoicePipelineEventHandler | None,
    ) -> UtteranceEvent | None:
        event = segmenter.accept_event(frame)
        if segmenter.is_recording and not state.was_recording:
            state.speech_started_at = time.perf_counter()
            state.post_activation_deadline = None
            self._emit(on_event, "speech", "started")
        if event is not None and event.kind == "resumed":
            self._emit(on_event, "speech", "resumed")
        state.was_recording = segmenter.is_recording
        return event

    def finish_with_utterance(
        self,
        state: CaptureState,
        utterance: DetectedUtterance,
        microphone: MicrophoneStream,
        listen_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ) -> CaptureResult:
        return finish_with_utterance_result(
            state,
            utterance,
            microphone,
            listen_started_at,
            lambda stage, message: self._emit(on_event, stage, message),
        )

    def finish_mode_switch(
        self,
        state: CaptureState,
        listen_started_at: float,
    ) -> CaptureResult:
        return finish_mode_switch_result(state, listen_started_at)

    def _duration(self, frames: list[np.ndarray]) -> float:
        return sum(len(frame) for frame in frames) / self._config.audio.sample_rate

    def _emit(
        self,
        on_event: VoicePipelineEventHandler | None,
        stage: str,
        message: str,
    ) -> None:
        if on_event is not None:
            on_event(stage, message)
