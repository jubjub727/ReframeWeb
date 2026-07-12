from __future__ import annotations

import time
from collections import deque

import numpy as np

from baml_sdk import context as baml_context
from reframe_agent_host.voice.activity import (
    UtteranceSegmenter,
    create_voice_activity_detector,
)
from reframe_agent_host.voice.capture_state import CaptureState
from reframe_agent_host.voice.debug_audio import DebugAudioRecorder
from reframe_agent_host.voice.types import VoicePipelineConfig


def create_segmenter(config: VoicePipelineConfig) -> UtteranceSegmenter:
    detector = create_voice_activity_detector(config.voice_activity)
    return UtteranceSegmenter(detector, config.voice_activity)


def create_capture_state(
    config: VoicePipelineConfig,
    conversation_mode: baml_context.ConversationMode,
) -> CaptureState:
    return CaptureState(
        conversation_mode=conversation_mode,
        keyphrase_required=conversation_mode == baml_context.ConversationMode.WAKE_COMMAND,
        keyphrase_carry_frames=frame_deque(
            config,
            config.keyphrases.carry_ms,
        ),
    )


def create_debug_audio(config: VoicePipelineConfig) -> DebugAudioRecorder:
    return DebugAudioRecorder(
        config.debug_audio_dir,
        config.audio.sample_rate,
        config.debug_audio_seconds,
        period_seconds=config.debug_audio_period_seconds,
    )


def frame_deque(
    config: VoicePipelineConfig,
    duration_ms: int,
) -> deque[np.ndarray]:
    return deque(
        maxlen=max(
            1,
            round(duration_ms / config.voice_activity.chunk_ms),
        )
    )


def listen_deadline(config: VoicePipelineConfig) -> float | None:
    if config.listen_timeout_seconds <= 0:
        return None
    return time.monotonic() + config.listen_timeout_seconds


def listen_timed_out(deadline: float | None, state: CaptureState) -> bool:
    if deadline is None:
        return False
    if state.keyphrase_detection is not None or state.speech_started_at is not None:
        return False
    return time.monotonic() >= deadline


def timeout_message(state: CaptureState) -> str:
    if state.keyphrase_required and state.keyphrase_detection is None:
        return "No keyphrase was detected before timeout."
    return "No complete utterance was detected before timeout."
