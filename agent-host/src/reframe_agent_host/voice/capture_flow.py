from __future__ import annotations

import time

import numpy as np

from reframe_agent_host.voice.microphone import MicrophoneStream
from reframe_agent_host.voice.activity import DetectedUtterance, UtteranceSegmenter
from reframe_agent_host.voice.vad_types import UtteranceEvent
from reframe_agent_host.voice.capture_results import (
    emit_microphone_warnings,
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

    def finish_conversation_mode_confirmation(
        self,
        result: KeyphraseGateResult,
        state: CaptureState,
        microphone: MicrophoneStream,
        listen_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ) -> CaptureResult | None:
        if not result.replay_frames:
            self._emit(on_event, "keyphrase", "no confirmation audio to transcribe")
            return None

        self._emit(on_event, "keyphrase", "confirming conversation mode phrase")
        samples = np.concatenate(
            [
                np.asarray(frame, dtype=np.float32).reshape(-1)
                for frame in result.replay_frames
            ]
        )
        ended_at = time.perf_counter()
        emit_microphone_warnings(
            microphone,
            lambda stage, message: self._emit(on_event, stage, message),
        )
        return CaptureResult(
            conversation_mode=state.conversation_mode,
            keyphrase_detection=state.keyphrase_detection,
            utterance=DetectedUtterance(
                samples=samples,
                sample_rate=self._config.audio.sample_rate,
                duration_seconds=len(samples) / self._config.audio.sample_rate,
                forced_end=True,
            ),
            mode_switched=False,
            keyphrase_wait_seconds=state.keyphrase_wait_seconds,
            listen_seconds=ended_at - listen_started_at,
            wait_for_speech_seconds=None,
            speech_capture_wall_seconds=len(samples) / self._config.audio.sample_rate,
        )

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
            self._emit(
                on_event,
                "speech",
                f"started detector={segmenter.detector_name}",
            )
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
            self._emit(
                on_event,
                "speech",
                f"started detector={segmenter.detector_name}",
            )
        if event is not None and event.kind == "resumed":
            self._emit(
                on_event,
                "speech",
                f"resumed detector={segmenter.detector_name}",
            )
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
