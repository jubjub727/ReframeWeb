from __future__ import annotations

import time
from collections.abc import Callable

from reframe_agent_host.voice.activity import DetectedUtterance
from reframe_agent_host.voice.capture_state import CaptureState
from reframe_agent_host.voice.microphone import MicrophoneStream
from reframe_agent_host.voice.capture_types import CaptureResult


EventEmitter = Callable[[str, str], None]


def finish_with_utterance_result(
    state: CaptureState,
    utterance: DetectedUtterance,
    microphone: MicrophoneStream,
    listen_started_at: float,
    emit: EventEmitter,
) -> CaptureResult:
    speech_ended_at = time.perf_counter()
    emit(
        "speech",
        "ended" + (" at max utterance length" if utterance.forced_end else ""),
    )
    emit_microphone_warnings(microphone, emit)
    return CaptureResult(
        conversation_mode=state.conversation_mode,
        keyphrase_detection=state.keyphrase_detection,
        utterance=utterance,
        mode_switched=state.mode_switched,
        keyphrase_wait_seconds=state.keyphrase_wait_seconds,
        listen_seconds=speech_ended_at - listen_started_at,
        wait_for_speech_seconds=(
            state.speech_started_at - listen_started_at
            if state.speech_started_at is not None
            else None
        ),
        speech_capture_wall_seconds=(
            speech_ended_at - state.speech_started_at
            if state.speech_started_at is not None
            else None
        ),
    )


def finish_mode_switch_result(
    state: CaptureState,
    listen_started_at: float,
) -> CaptureResult:
    ended_at = time.perf_counter()
    return CaptureResult(
        conversation_mode=state.conversation_mode,
        keyphrase_detection=state.keyphrase_detection,
        utterance=None,
        mode_switched=state.mode_switched,
        keyphrase_wait_seconds=state.keyphrase_wait_seconds,
        listen_seconds=ended_at - listen_started_at,
        wait_for_speech_seconds=None,
        speech_capture_wall_seconds=None,
    )


def emit_microphone_warnings(
    microphone: MicrophoneStream,
    emit: EventEmitter,
) -> None:
    if microphone.dropped_frames:
        emit("warning", f"dropped {microphone.dropped_frames} audio chunks")
    if microphone.last_status:
        emit("warning", microphone.last_status)
