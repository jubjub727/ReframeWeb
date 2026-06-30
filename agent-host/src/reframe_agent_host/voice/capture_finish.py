from __future__ import annotations

from collections.abc import Callable

from reframe_agent_host.voice.activity import DetectedUtterance
from reframe_agent_host.voice.capture_flow import VoiceCaptureFlow
from reframe_agent_host.voice.capture_state import CaptureState
from reframe_agent_host.voice.debug_audio import DebugAudioRecorder
from reframe_agent_host.voice.microphone import MicrophoneStream
from reframe_agent_host.voice.types import (
    CaptureResult,
    VoicePipelineEventHandler,
)


EventEmitter = Callable[[str, str], None]


def finish_with_debug_audio(
    flow: VoiceCaptureFlow,
    state: CaptureState,
    utterance: DetectedUtterance,
    microphone: MicrophoneStream,
    listen_started_at: float,
    debug_audio: DebugAudioRecorder,
    emit: EventEmitter,
    on_event: VoicePipelineEventHandler | None,
) -> CaptureResult:
    result = flow.finish_with_utterance(
        state,
        utterance,
        microphone,
        listen_started_at,
        on_event,
    )
    debug_audio.save_and_emit(
        "utterance",
        emit,
        {
            "duration_seconds": utterance.duration_seconds,
            "keyphrase": (
                state.keyphrase_detection.phrase
                if state.keyphrase_detection is not None
                else None
            ),
        },
    )
    return result
