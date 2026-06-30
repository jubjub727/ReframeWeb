from __future__ import annotations

import time

from reframe_agent_host.voice.microphone import MicrophoneStream
from reframe_agent_host.baml_client import types
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
    timeout_message,
)
from reframe_agent_host.voice.capture_state import CaptureState
from reframe_agent_host.voice.keyphrase_gate import VoiceKeyphraseGate
from reframe_agent_host.voice.types import (
    CaptureResult,
    VoicePipelineConfig,
    VoicePipelineEventHandler,
)


class VoiceTurnCapture:
    def __init__(
        self,
        config: VoicePipelineConfig,
        conversation_mode: types.ConversationMode,
    ) -> None:
        self._config = config
        self._conversation_mode = conversation_mode
        self._flow = VoiceCaptureFlow(config)
        self._router = CaptureFrameRouter(config, self._flow)

    def capture(
        self,
        on_event: VoicePipelineEventHandler | None,
    ) -> CaptureResult:
        segmenter = create_segmenter(self._config)
        state = create_capture_state(self._config, self._conversation_mode)
        keyphrase_gate = VoiceKeyphraseGate(self._config)
        debug_audio = create_debug_audio(self._config)
        deadline = listen_deadline(self._config)
        listen_started_at = time.perf_counter()

        self._emit_listening(on_event, segmenter, state)
        with MicrophoneStream(self._config.audio) as microphone:
            try:
                self._emit_audio_source(on_event, microphone)
                if state.keyphrase_required:
                    keyphrase_gate.start(state, self._emitter(on_event))

                for frame in microphone.frames():
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
                state.close_spotters()

        raise RuntimeError("Microphone stream closed before an utterance was detected.")

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
                f"channel={self._config.audio.channel} "
                f"-> processing={self._config.audio.sample_rate} Hz "
                f"gain={self._config.audio.input_gain:g}x"
            ),
        )
