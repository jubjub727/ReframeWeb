from __future__ import annotations

import time
from collections.abc import Callable
from threading import Event

import baml_sdk as types
from reframe_agent_host.voice.activity import UtteranceSegmenter
from reframe_agent_host.voice.capture_finish import finish_with_debug_audio
from reframe_agent_host.voice.capture_flow import VoiceCaptureFlow
from reframe_agent_host.voice.capture_setup import (
    create_capture_state,
    create_debug_audio,
    create_segmenter,
    listen_deadline,
    timeout_message,
)
from reframe_agent_host.voice.capture_state import CaptureState
from reframe_agent_host.voice.conversation_mode import ConversationModeController
from reframe_agent_host.voice.microphone import MicrophoneStream
from reframe_agent_host.voice.keyphrase_gate import VoiceKeyphraseGate
from reframe_agent_host.voice.types import (
    CaptureResult,
    CaptureStreamEvent,
    VoicePipelineConfig,
    VoicePipelineEventHandler,
)


CaptureStreamEventHandler = Callable[[CaptureStreamEvent], None]


class SpeculativeCaptureSession:
    def __init__(
        self,
        config: VoicePipelineConfig,
        conversation_mode: types.ConversationMode,
        mode_controller: ConversationModeController | None = None,
    ) -> None:
        self._config = config
        self._conversation_mode = conversation_mode
        self._mode_controller = mode_controller
        self._mode_version = (
            mode_controller.snapshot()[1] if mode_controller is not None else 0
        )
        self._flow = VoiceCaptureFlow(config)

    def run(
        self,
        on_event: VoicePipelineEventHandler | None,
        on_capture_event: CaptureStreamEventHandler,
        stop_event: Event | None = None,
        max_turns: int = 0,
    ) -> None:
        turn_id = 0
        pending_turn_id: int | None = None
        pending_capture: CaptureResult | None = None
        completed_turns = 0

        def next_turn_id() -> int:
            nonlocal turn_id
            turn_id += 1
            return turn_id

        def emit_endpoint(result: CaptureResult) -> None:
            nonlocal pending_capture, pending_turn_id
            current_turn_id = next_turn_id()
            on_capture_event(CaptureStreamEvent("endpoint", current_turn_id, result))
            if self._endpoint_is_final(result):
                on_capture_event(CaptureStreamEvent("confirmed", current_turn_id, result))
                pending_turn_id = None
                pending_capture = None
                return
            pending_turn_id = current_turn_id
            pending_capture = result

        def turn_finished(result: CaptureResult) -> bool:
            nonlocal completed_turns
            self._conversation_mode = result.conversation_mode
            if self._mode_controller is not None:
                self._mode_controller.set(result.conversation_mode)
                self._mode_version = self._mode_controller.snapshot()[1]
            completed_turns += 1
            return max_turns > 0 and completed_turns >= max_turns

        input_started = False
        state: CaptureState | None = None
        try:
            with MicrophoneStream(self._config.audio) as microphone:
                input_started = True
                self._emit_input_started(on_event)
                self._emit_audio_source(on_event, microphone)
                (
                    segmenter,
                    state,
                    keyphrase_gate,
                    debug_audio,
                    deadline,
                    listen_started_at,
                ) = self._start_turn(on_event)

                for frame in microphone.frames(stop_event=stop_event):
                    if stop_event is not None and stop_event.is_set():
                        raise InterruptedError("Voice capture was stopped.")

                    if self._sync_external_mode_change(state, on_event):
                        pending_turn_id = None
                        pending_capture = None
                        state.close_spotters()
                        (
                            segmenter,
                            state,
                            keyphrase_gate,
                            debug_audio,
                            deadline,
                            listen_started_at,
                        ) = self._start_turn(on_event)
                        continue

                    debug_audio.append(frame)
                    debug_audio.maybe_save_periodic(self._emitter(on_event))

                    if state.keyphrase_required and state.keyphrase_detection is None:
                        result = self._accept_keyphrase_frame(
                            frame,
                            keyphrase_gate,
                            segmenter,
                            state,
                            listen_started_at,
                            microphone,
                            debug_audio,
                            on_event,
                        )
                        if result is not None:
                            emit_endpoint(result)
                            if self._endpoint_is_final(result):
                                if turn_finished(result):
                                    return
                                state.close_spotters()
                                (
                                    segmenter,
                                    state,
                                    keyphrase_gate,
                                    debug_audio,
                                    deadline,
                                    listen_started_at,
                                ) = self._start_turn(on_event)
                        continue

                    event = self._flow.accept_speech_event(
                        frame,
                        segmenter,
                        state,
                        on_event,
                    )
                    if event is not None and event.kind == "endpoint":
                        assert event.utterance is not None
                        result = finish_with_debug_audio(
                            self._flow,
                            state,
                            event.utterance,
                            microphone,
                            listen_started_at,
                            debug_audio,
                            self._emitter(on_event),
                            on_event,
                        )
                        emit_endpoint(result)
                        if self._endpoint_is_final(result):
                            if turn_finished(result):
                                return
                            state.close_spotters()
                            (
                                segmenter,
                                state,
                                keyphrase_gate,
                                debug_audio,
                                deadline,
                                listen_started_at,
                            ) = self._start_turn(on_event)
                    elif event is not None and event.kind == "resumed":
                        if pending_turn_id is not None:
                            on_capture_event(
                                CaptureStreamEvent("resumed", pending_turn_id)
                            )
                            pending_turn_id = None
                            pending_capture = None
                    elif event is not None and event.kind == "confirmed":
                        if pending_turn_id is not None and pending_capture is not None:
                            on_capture_event(
                                CaptureStreamEvent(
                                    "confirmed",
                                    pending_turn_id,
                                    pending_capture,
                                )
                            )
                            result = pending_capture
                            pending_turn_id = None
                            pending_capture = None
                            if turn_finished(result):
                                return
                            state.close_spotters()
                            (
                                segmenter,
                                state,
                                keyphrase_gate,
                                debug_audio,
                                deadline,
                                listen_started_at,
                            ) = self._start_turn(on_event)

                    if self._activation_window_expired(state):
                        current_turn_id = next_turn_id()
                        result = self._flow.finish_mode_switch(state, listen_started_at)
                        on_capture_event(
                            CaptureStreamEvent("mode_switch", current_turn_id, result)
                        )
                        if turn_finished(result):
                            return
                        state.close_spotters()
                        (
                            segmenter,
                            state,
                            keyphrase_gate,
                            debug_audio,
                            deadline,
                            listen_started_at,
                        ) = self._start_turn(on_event)

                    if deadline is not None and time.monotonic() >= deadline:
                        debug_audio.save_and_emit(
                            "timeout",
                            self._emitter(on_event),
                            {
                                "message": timeout_message(state),
                                "dropped_frames": microphone.dropped_frames,
                                "microphone_status": microphone.last_status,
                            },
                        )
                        raise TimeoutError(timeout_message(state))
        finally:
            if state is not None:
                state.close_spotters()
            if input_started:
                self._emit_input_stopped(on_event)

        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Voice capture was stopped.")
        raise RuntimeError("Microphone stream closed before an utterance was detected.")

    def _start_turn(
        self,
        on_event: VoicePipelineEventHandler | None,
    ):
        if self._mode_controller is not None:
            self._conversation_mode, self._mode_version = (
                self._mode_controller.snapshot()
            )
        segmenter = create_segmenter(self._config)
        state = create_capture_state(self._config, self._conversation_mode)
        keyphrase_gate = VoiceKeyphraseGate(self._config)
        debug_audio = create_debug_audio(self._config)
        if state.keyphrase_required:
            keyphrase_gate.start(state, self._emitter(on_event))
        deadline = listen_deadline(self._config)
        listen_started_at = time.perf_counter()
        self._emit_listening(on_event, segmenter, state)
        return segmenter, state, keyphrase_gate, debug_audio, deadline, listen_started_at

    def _sync_external_mode_change(
        self,
        state: CaptureState,
        on_event: VoicePipelineEventHandler | None,
    ) -> bool:
        if self._mode_controller is None:
            return False

        mode, version = self._mode_controller.snapshot()
        if version == self._mode_version:
            return False

        self._mode_version = version
        if mode == state.conversation_mode:
            return False

        self._conversation_mode = mode
        self._emit(on_event, "conversation-mode", mode.value)
        return True

    def _accept_keyphrase_frame(
        self,
        frame,
        keyphrase_gate: VoiceKeyphraseGate,
        segmenter: UtteranceSegmenter,
        state: CaptureState,
        listen_started_at: float,
        microphone: MicrophoneStream,
        debug_audio,
        on_event: VoicePipelineEventHandler | None,
    ) -> CaptureResult | None:
        result = keyphrase_gate.accept(
            frame,
            state,
            listen_started_at,
            self._emitter(on_event),
        )
        if result is None:
            return None

        debug_audio.save_and_emit(
            f"keyphrase-{result.detection.phrase}",
            self._emitter(on_event),
            {"hypstr": result.detection.hypstr, "kind": result.detection.kind},
        )
        if result.conversation_enabled:
            return self._flow.enable_conversation_mode(
                result,
                state,
                segmenter,
                microphone,
                listen_started_at,
                on_event,
            )

        utterance = self._flow.replay_wake_audio(result, segmenter, state, on_event)
        if utterance is None:
            return None
        return finish_with_debug_audio(
            self._flow,
            state,
            utterance,
            microphone,
            listen_started_at,
            debug_audio,
            self._emitter(on_event),
            on_event,
        )

    def _endpoint_is_final(self, result: CaptureResult) -> bool:
        return (
            result.utterance is not None
            and (
                result.utterance.forced_end
                or self._config.voice_activity.final_silence_ms
                <= self._config.voice_activity.min_silence_ms
            )
        )

    def _activation_window_expired(self, state: CaptureState) -> bool:
        return (
            state.mode_switched
            and state.post_activation_deadline is not None
            and time.perf_counter() >= state.post_activation_deadline
        )

    def _emit_listening(
        self,
        on_event: VoicePipelineEventHandler | None,
        segmenter: UtteranceSegmenter,
        state: CaptureState,
    ) -> None:
        self._emit(
            on_event,
            "listening",
            f"device={self._config.audio.device or 'default'} "
            f"vad={segmenter.detector_name} "
            f"keyphrase={'on' if state.keyphrase_required else 'off'}",
        )

    def _emitter(self, on_event: VoicePipelineEventHandler | None):
        return lambda stage, message: self._emit(on_event, stage, message)

    def _emit(
        self,
        on_event: VoicePipelineEventHandler | None,
        stage: str,
        message: str,
    ) -> None:
        if on_event is not None:
            on_event(stage, message)

    def _emit_audio_source(
        self,
        on_event: VoicePipelineEventHandler | None,
        microphone: MicrophoneStream,
    ) -> None:
        self._emit(
            on_event,
            "audio",
            (
                f"input={microphone.device_summary} "
                f"channels={microphone.input_channels} "
                f"channel={_channel_label(self._config.audio.channel)} "
                f"-> processing={self._config.audio.sample_rate} Hz "
                f"gain={self._config.audio.input_gain:g}x "
                f"limiter={self._config.audio.limiter_ceiling:g}"
            ),
        )

    def _emit_input_started(
        self,
        on_event: VoicePipelineEventHandler | None,
    ) -> None:
        self._emit(on_event, "input-started", "microphone stream opened")

    def _emit_input_stopped(
        self,
        on_event: VoicePipelineEventHandler | None,
    ) -> None:
        self._emit(on_event, "input-stopped", "microphone stream closed")


def _channel_label(channel: int) -> str:
    return "auto" if channel < 0 else str(channel)
