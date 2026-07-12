from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np

from reframe_agent_host.voice.activity import UtteranceSegmenter
from reframe_agent_host.voice.capture_finish import finish_with_debug_audio
from reframe_agent_host.voice.capture_flow import VoiceCaptureFlow
from reframe_agent_host.voice.capture_state import CaptureState
from reframe_agent_host.voice.debug_audio import DebugAudioRecorder
from reframe_agent_host.voice.keyphrase_gate import VoiceKeyphraseGate
from reframe_agent_host.voice.microphone import MicrophoneStream
from reframe_agent_host.voice.capture_types import CaptureResult
from reframe_agent_host.voice.pipeline_config import (
    VoicePipelineConfig,
    VoicePipelineEventHandler,
)


EventEmitter = Callable[[str, str], None]


class CaptureFrameRouter:
    def __init__(self, config: VoicePipelineConfig, flow: VoiceCaptureFlow) -> None:
        self._config = config
        self._flow = flow

    def accept_frame(
        self,
        frame: np.ndarray,
        keyphrase_gate: VoiceKeyphraseGate,
        segmenter: UtteranceSegmenter,
        state: CaptureState,
        listen_started_at: float,
        microphone: MicrophoneStream,
        debug_audio: DebugAudioRecorder,
        emit: EventEmitter,
        on_event: VoicePipelineEventHandler | None,
    ) -> CaptureResult | None:
        if state.keyphrase_required and state.keyphrase_detection is None:
            return self._accept_keyphrase_frame(
                frame,
                keyphrase_gate,
                segmenter,
                state,
                listen_started_at,
                microphone,
                debug_audio,
                emit,
                on_event,
            )
        return self._accept_utterance_frame(
            frame,
            segmenter,
            state,
            listen_started_at,
            microphone,
            debug_audio,
            emit,
            on_event,
        )

    def _accept_keyphrase_frame(
        self,
        frame: np.ndarray,
        keyphrase_gate: VoiceKeyphraseGate,
        segmenter: UtteranceSegmenter,
        state: CaptureState,
        listen_started_at: float,
        microphone: MicrophoneStream,
        debug_audio: DebugAudioRecorder,
        emit: EventEmitter,
        on_event: VoicePipelineEventHandler | None,
    ) -> CaptureResult | None:
        result = keyphrase_gate.accept(frame, state, listen_started_at, emit)
        if result is None:
            return None

        debug_audio.save_and_emit(
            f"keyphrase-{result.detection.phrase}",
            emit,
            {"hypstr": result.detection.hypstr, "kind": result.detection.kind},
        )
        if result.conversation_enabled:
            return self._flow.finish_conversation_mode_confirmation(
                result,
                state,
                microphone,
                listen_started_at,
                on_event,
            )

        utterance = self._flow.replay_wake_audio(result, segmenter, state, on_event)
        if utterance is None:
            return None
        return finish_with_debug_audio(
            self._flow, state, utterance, microphone, listen_started_at,
            debug_audio, emit, on_event,
        )

    def _accept_utterance_frame(
        self,
        frame: np.ndarray,
        segmenter: UtteranceSegmenter,
        state: CaptureState,
        listen_started_at: float,
        microphone: MicrophoneStream,
        debug_audio: DebugAudioRecorder,
        emit: EventEmitter,
        on_event: VoicePipelineEventHandler | None,
    ) -> CaptureResult | None:
        utterance = self._flow.accept_speech_frame(frame, segmenter, state, on_event)
        if utterance is not None:
            return finish_with_debug_audio(
                self._flow, state, utterance, microphone, listen_started_at,
                debug_audio, emit, on_event,
            )
        if self._activation_window_expired(state):
            return self._flow.finish_mode_switch(state, listen_started_at)
        return None

    def _activation_window_expired(self, state: CaptureState) -> bool:
        return (
            state.mode_switched
            and state.post_activation_deadline is not None
            and time.perf_counter() >= state.post_activation_deadline
        )
