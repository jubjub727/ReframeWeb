from __future__ import annotations

from reframe_agent_host.baml_client import types
from reframe_agent_host.speech.transcription import Transcript
from reframe_agent_host.speech.triggers import TriggerPhraseDetection
from reframe_agent_host.voice.pipeline_timings import (
    mode_switch_timings,
    turn_timings,
)
from reframe_agent_host.voice.types import (
    CaptureResult,
    VoicePipelineConfig,
    VoiceTurnResult,
)


def mode_switch_turn_result(
    capture: CaptureResult,
    conversation_mode: types.ConversationMode,
    model_prepare_seconds: float,
    total_started_at: float,
) -> VoiceTurnResult:
    return VoiceTurnResult(
        mode=conversation_mode,
        mode_switched=True,
        keyphrase_detection=capture.keyphrase_detection,
        trigger_detection=None,
        routed_transcript="",
        ignored=False,
        utterance=None,
        transcript=None,
        plan=None,
        timings=mode_switch_timings(
            model_prepare_seconds,
            capture,
            total_started_at,
        ),
    )


def transcribed_turn_result(
    config: VoicePipelineConfig,
    conversation_mode: types.ConversationMode,
    capture: CaptureResult,
    transcript: Transcript,
    trigger_detection: TriggerPhraseDetection | None,
    routed_transcript: str,
    plan: types.AgentTurnPlan | None,
    timings: dict[str, float | None],
) -> VoiceTurnResult:
    return VoiceTurnResult(
        mode=conversation_mode,
        mode_switched=capture.mode_switched,
        keyphrase_detection=capture.keyphrase_detection,
        trigger_detection=trigger_detection,
        routed_transcript=routed_transcript,
        ignored=False,
        utterance=capture.utterance,
        transcript=transcript,
        plan=plan,
        timings=turn_timings(
            config,
            model_prepare_seconds=timings["model_prepare_seconds"],
            capture=capture,
            total_started_at=timings["total_started_at"],
            post_vad_transcript_seconds=timings["post_vad_transcript_seconds"],
            post_vad_plan_seconds=timings["post_vad_plan_seconds"],
            transcription_seconds=timings["transcription_seconds"],
            planning_seconds=timings["planning_seconds"],
        ),
    )
