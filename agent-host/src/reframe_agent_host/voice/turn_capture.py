from __future__ import annotations

import time
from collections.abc import Callable
from threading import Event

from reframe_agent_host.voice.microphone import MicrophoneStream
import baml_sdk as types
from reframe_agent_host.voice.activity import (
    UtteranceSegmenter,
)
from reframe_agent_host.voice.capture_frame_router import CaptureFrameRouter
from reframe_agent_host.voice.capture_flow import VoiceCaptureFlow
from reframe_agent_host.voice.capture_setup import (
    create_capture_state,
    create_debug_audio,
    create_segmenter,
    listen_deadline,
    listen_timed_out,
    timeout_message,
)
from reframe_agent_host.voice.conversation_mode import ConversationModeController
from reframe_agent_host.voice.keyphrase_gate import VoiceKeyphraseGate
from reframe_agent_host.voice.speculative_capture_session import (
    SpeculativeCaptureSession,
)
from reframe_agent_host.voice.types import (
    CaptureStreamEvent,
    CaptureResult,
    VoicePipelineConfig,
    VoicePipelineEventHandler,
)


CaptureStreamEventHandler = Callable[[CaptureStreamEvent], None]


class VoiceTurnCapture:
    def __init__(
        self,
        config: VoicePipelineConfig,
        conversation_mode: types.ConversationMode,
        mode_controller: ConversationModeController | None = None,
    ) -> None:
        self._config = config
        self._conversation_mode = conversation_mode
        self._mode_controller = mode_controller
        self._flow = VoiceCaptureFlow(config)
        self._router = CaptureFrameRouter(config, self._flow)

    def capture(
        self,
        on_event: VoicePipelineEventHandler | None,
        stop_event: Event | None = None,
    ) -> CaptureResult:
        segmenter = create_segmenter(self._config)
        state = create_capture_state(self._config, self._conversation_mode)
        keyphrase_gate = VoiceKeyphraseGate(self._config)
        debug_audio = create_debug_audio(self._config)

        input_started = False
        try:
            with MicrophoneStream(self._config.audio) as microphone:
                input_started = True
                self._emit_input_started(on_event)
                self._emit_audio_source(on_event, microphone)
                if state.keyphrase_required:
                    keyphrase_gate.start(state, self._emitter(on_event))

                deadline = listen_deadline(self._config)
                listen_started_at = time.perf_counter()
                self._emit_listening(on_event, segmenter, state)

                for frame in microphone.frames(stop_event=stop_event):
                    if stop_event is not None and stop_event.is_set():
                        raise InterruptedError("Voice capture was stopped.")
                    debug_audio.append(frame)
                    debug_audio.maybe_save_periodic(self._emitter(on_event))
                    result = self._router.accept_frame(
                        frame,
                        keyphrase_gate,
                        segmenter,
                        state,
                        listen_started_at,
                        microphone,
                        debug_audio,
                        self._emitter(on_event),
                        on_event,
                    )
                    if result is not None:
                        return result

                    if listen_timed_out(deadline, state):
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
            state.close_spotters()
            if input_started:
                self._emit_input_stopped(on_event)

        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Voice capture was stopped.")
        raise RuntimeError("Microphone stream closed before an utterance was detected.")

    def capture_speculative_once(
        self,
        on_event: VoicePipelineEventHandler | None,
        on_capture_event: CaptureStreamEventHandler,
        stop_event: Event | None = None,
    ) -> None:
        self.capture_speculative_session(on_event, on_capture_event, stop_event, 1)

    def capture_speculative_session(
        self,
        on_event: VoicePipelineEventHandler | None,
        on_capture_event: CaptureStreamEventHandler,
        stop_event: Event | None = None,
        max_turns: int = 0,
    ) -> None:
        SpeculativeCaptureSession(
            self._config,
            self._conversation_mode,
            mode_controller=self._mode_controller,
        ).run(
            on_event,
            on_capture_event,
            stop_event=stop_event,
            max_turns=max_turns,
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
