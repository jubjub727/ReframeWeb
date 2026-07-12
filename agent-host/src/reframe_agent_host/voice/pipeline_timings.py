from __future__ import annotations

import time

from reframe_agent_host.voice.capture_types import CaptureResult
from reframe_agent_host.voice.pipeline_config import VoicePipelineConfig
from reframe_agent_host.voice.turn_data import VoiceTurnTimings


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
        post_vad_task_choice_seconds=None,
        post_vad_memory_search_seconds=None,
        post_vad_search_depth_seconds=None,
        post_vad_memory_retrieval_seconds=None,
        post_vad_memory_relevance_seconds=None,
        post_vad_task_prompt_seconds=None,
        post_vad_task_execution_seconds=None,
        post_vad_primitive_dispatch_seconds=None,
        post_vad_action_history_summary_seconds=None,
        post_vad_task_completion_seconds=None,
        estimated_user_stop_to_transcript_seconds=None,
        estimated_user_stop_to_task_choice_seconds=None,
        estimated_user_stop_to_memory_search_seconds=None,
        estimated_user_stop_to_search_depth_seconds=None,
        estimated_user_stop_to_memory_retrieval_seconds=None,
        estimated_user_stop_to_memory_relevance_seconds=None,
        estimated_user_stop_to_task_prompt_seconds=None,
        estimated_user_stop_to_task_execution_seconds=None,
        estimated_user_stop_to_primitive_dispatch_seconds=None,
        estimated_user_stop_to_action_history_summary_seconds=None,
        estimated_user_stop_to_task_completion_seconds=None,
        transcription_seconds=None,
        task_choice_seconds=None,
        memory_search_seconds=None,
        search_depth_seconds=None,
        memory_retrieval_seconds=None,
        memory_relevance_seconds=None,
        task_prompt_seconds=None,
        task_execution_seconds=None,
        primitive_dispatch_seconds=None,
        action_history_summary_seconds=None,
        task_completion_seconds=None,
        total_seconds=time.perf_counter() - total_started_at,
    )


def turn_timings(
    config: VoicePipelineConfig,
    model_prepare_seconds: float,
    capture: CaptureResult,
    total_started_at: float,
    post_vad_transcript_seconds: float,
    post_vad_task_choice_seconds: float | None,
    post_vad_memory_search_seconds: float | None,
    post_vad_search_depth_seconds: float | None,
    post_vad_memory_retrieval_seconds: float | None,
    post_vad_memory_relevance_seconds: float | None,
    post_vad_task_prompt_seconds: float | None,
    post_vad_task_execution_seconds: float | None,
    post_vad_primitive_dispatch_seconds: float | None,
    post_vad_action_history_summary_seconds: float | None,
    post_vad_task_completion_seconds: float | None,
    transcription_seconds: float,
    task_choice_seconds: float | None,
    memory_search_seconds: float | None,
    search_depth_seconds: float | None,
    memory_retrieval_seconds: float | None,
    memory_relevance_seconds: float | None,
    task_prompt_seconds: float | None,
    task_execution_seconds: float | None,
    primitive_dispatch_seconds: float | None,
    action_history_summary_seconds: float | None,
    task_completion_seconds: float | None,
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
        post_vad_task_choice_seconds=post_vad_task_choice_seconds,
        post_vad_memory_search_seconds=post_vad_memory_search_seconds,
        post_vad_search_depth_seconds=post_vad_search_depth_seconds,
        post_vad_memory_retrieval_seconds=post_vad_memory_retrieval_seconds,
        post_vad_memory_relevance_seconds=post_vad_memory_relevance_seconds,
        post_vad_task_prompt_seconds=post_vad_task_prompt_seconds,
        post_vad_task_execution_seconds=post_vad_task_execution_seconds,
        post_vad_primitive_dispatch_seconds=post_vad_primitive_dispatch_seconds,
        post_vad_action_history_summary_seconds=(
            post_vad_action_history_summary_seconds
        ),
        post_vad_task_completion_seconds=post_vad_task_completion_seconds,
        estimated_user_stop_to_transcript_seconds=(
            vad_delay_seconds + post_vad_transcript_seconds
        ),
        estimated_user_stop_to_task_choice_seconds=(
            vad_delay_seconds + post_vad_task_choice_seconds
            if post_vad_task_choice_seconds is not None
            else None
        ),
        estimated_user_stop_to_memory_search_seconds=(
            vad_delay_seconds + post_vad_memory_search_seconds
            if post_vad_memory_search_seconds is not None
            else None
        ),
        estimated_user_stop_to_search_depth_seconds=(
            vad_delay_seconds + post_vad_search_depth_seconds
            if post_vad_search_depth_seconds is not None
            else None
        ),
        estimated_user_stop_to_memory_retrieval_seconds=(
            vad_delay_seconds + post_vad_memory_retrieval_seconds
            if post_vad_memory_retrieval_seconds is not None
            else None
        ),
        estimated_user_stop_to_memory_relevance_seconds=(
            vad_delay_seconds + post_vad_memory_relevance_seconds
            if post_vad_memory_relevance_seconds is not None
            else None
        ),
        estimated_user_stop_to_task_prompt_seconds=(
            vad_delay_seconds + post_vad_task_prompt_seconds
            if post_vad_task_prompt_seconds is not None
            else None
        ),
        estimated_user_stop_to_task_execution_seconds=(
            vad_delay_seconds + post_vad_task_execution_seconds
            if post_vad_task_execution_seconds is not None
            else None
        ),
        estimated_user_stop_to_primitive_dispatch_seconds=(
            vad_delay_seconds + post_vad_primitive_dispatch_seconds
            if post_vad_primitive_dispatch_seconds is not None
            else None
        ),
        estimated_user_stop_to_action_history_summary_seconds=(
            vad_delay_seconds + post_vad_action_history_summary_seconds
            if post_vad_action_history_summary_seconds is not None
            else None
        ),
        estimated_user_stop_to_task_completion_seconds=(
            vad_delay_seconds + post_vad_task_completion_seconds
            if post_vad_task_completion_seconds is not None
            else None
        ),
        transcription_seconds=transcription_seconds,
        task_choice_seconds=task_choice_seconds,
        memory_search_seconds=memory_search_seconds,
        search_depth_seconds=search_depth_seconds,
        memory_retrieval_seconds=memory_retrieval_seconds,
        memory_relevance_seconds=memory_relevance_seconds,
        task_prompt_seconds=task_prompt_seconds,
        task_execution_seconds=task_execution_seconds,
        primitive_dispatch_seconds=primitive_dispatch_seconds,
        action_history_summary_seconds=action_history_summary_seconds,
        task_completion_seconds=task_completion_seconds,
        total_seconds=time.perf_counter() - total_started_at,
    )
