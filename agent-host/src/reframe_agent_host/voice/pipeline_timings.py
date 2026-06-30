from __future__ import annotations

import time

from reframe_agent_host.voice.types import (
    CaptureResult,
    VoicePipelineConfig,
    VoiceTurnTimings,
)


def mode_switch_timings(
    model_prepare_seconds: float,
    capture: CaptureResult,
    total_started_at: float,
) -> VoiceTurnTimings:
    return VoiceTurnTimings(
        model_prepare_seconds=model_prepare_seconds,
        keyphrase_wait_seconds=capture.keyphrase_wait_seconds,
        listen_seconds=capture.listen_seconds,
        wait_for_speech_seconds=None,
        speech_capture_wall_seconds=None,
        vad_endpoint_delay_estimate_seconds=0.0,
        post_vad_transcript_seconds=None,
        post_vad_plan_seconds=None,
        estimated_user_stop_to_transcript_seconds=None,
        estimated_user_stop_to_plan_seconds=None,
        transcription_seconds=None,
        planning_seconds=None,
        total_seconds=time.perf_counter() - total_started_at,
    )


def turn_timings(
    config: VoicePipelineConfig,
    model_prepare_seconds: float,
    capture: CaptureResult,
    total_started_at: float,
    post_vad_transcript_seconds: float,
    post_vad_plan_seconds: float | None,
    transcription_seconds: float,
    planning_seconds: float | None,
) -> VoiceTurnTimings:
    vad_delay_seconds = config.voice_activity.min_silence_ms / 1000
    return VoiceTurnTimings(
        model_prepare_seconds=model_prepare_seconds,
        keyphrase_wait_seconds=capture.keyphrase_wait_seconds,
        listen_seconds=capture.listen_seconds,
        wait_for_speech_seconds=capture.wait_for_speech_seconds,
        speech_capture_wall_seconds=capture.speech_capture_wall_seconds,
        vad_endpoint_delay_estimate_seconds=vad_delay_seconds,
        post_vad_transcript_seconds=post_vad_transcript_seconds,
        post_vad_plan_seconds=post_vad_plan_seconds,
        estimated_user_stop_to_transcript_seconds=(
            vad_delay_seconds + post_vad_transcript_seconds
        ),
        estimated_user_stop_to_plan_seconds=(
            vad_delay_seconds + post_vad_plan_seconds
            if post_vad_plan_seconds is not None
            else None
        ),
        transcription_seconds=transcription_seconds,
        planning_seconds=planning_seconds,
        total_seconds=time.perf_counter() - total_started_at,
    )
