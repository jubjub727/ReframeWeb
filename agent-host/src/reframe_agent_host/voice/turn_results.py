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
from reframe_memory import RetrievedMemoryContext


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
        task_choice=None,
        memory_search_hints=None,
        search_depths=None,
        retrieved_memories=None,
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
    task_choice: types.TaskChoiceDecision | None,
    memory_search_hints: types.ConversationMemorySearchHints | None,
    search_depths: types.SearchDepthDecision | None,
    retrieved_memories: RetrievedMemoryContext | None,
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
        task_choice=task_choice,
        memory_search_hints=memory_search_hints,
        search_depths=search_depths,
        retrieved_memories=retrieved_memories,
        timings=turn_timings(
            config,
            model_prepare_seconds=timings["model_prepare_seconds"],
            capture=capture,
            total_started_at=timings["total_started_at"],
            post_vad_transcript_seconds=timings["post_vad_transcript_seconds"],
            post_vad_task_choice_seconds=timings["post_vad_task_choice_seconds"],
            post_vad_memory_search_seconds=timings["post_vad_memory_search_seconds"],
            post_vad_search_depth_seconds=timings["post_vad_search_depth_seconds"],
            post_vad_memory_retrieval_seconds=timings[
                "post_vad_memory_retrieval_seconds"
            ],
            transcription_seconds=timings["transcription_seconds"],
            task_choice_seconds=timings["task_choice_seconds"],
            memory_search_seconds=timings["memory_search_seconds"],
            search_depth_seconds=timings["search_depth_seconds"],
            memory_retrieval_seconds=timings["memory_retrieval_seconds"],
        ),
    )
