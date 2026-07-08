from __future__ import annotations

import baml_sdk as types
from reframe_agent_host.speech.transcription import Transcript
from reframe_agent_host.speech.triggers import TriggerPhraseDetection
from reframe_agent_host.task_execution import PrimitiveDispatchResult
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
        relevance_decision=None,
        relevant_memories=None,
        selected_memory_contexts=None,
        task_prompt=None,
        task_execution=None,
        primitive_dispatch=None,
        action_history_summary=None,
        timings=mode_switch_timings(
            model_prepare_seconds,
            capture,
            total_started_at,
        ),
    )


def ignored_turn_result(
    config: VoicePipelineConfig,
    capture: CaptureResult,
    conversation_mode: types.ConversationMode,
    model_prepare_seconds: float,
    total_started_at: float,
) -> VoiceTurnResult:
    return VoiceTurnResult(
        mode=conversation_mode,
        mode_switched=capture.mode_switched,
        keyphrase_detection=capture.keyphrase_detection,
        trigger_detection=None,
        routed_transcript="",
        ignored=True,
        utterance=capture.utterance,
        transcript=None,
        task_choice=None,
        memory_search_hints=None,
        search_depths=None,
        retrieved_memories=None,
        relevance_decision=None,
        relevant_memories=None,
        selected_memory_contexts=None,
        task_prompt=None,
        task_execution=None,
        primitive_dispatch=None,
        action_history_summary=None,
        timings=turn_timings(
            config,
            model_prepare_seconds=model_prepare_seconds,
            capture=capture,
            total_started_at=total_started_at,
            post_vad_transcript_seconds=0.0,
            post_vad_task_choice_seconds=None,
            post_vad_memory_search_seconds=None,
            post_vad_search_depth_seconds=None,
            post_vad_memory_retrieval_seconds=None,
            post_vad_memory_relevance_seconds=None,
            post_vad_task_prompt_seconds=None,
            post_vad_task_execution_seconds=None,
            post_vad_primitive_dispatch_seconds=None,
            post_vad_action_history_summary_seconds=None,
            transcription_seconds=0.0,
            task_choice_seconds=None,
            memory_search_seconds=None,
            search_depth_seconds=None,
            memory_retrieval_seconds=None,
            memory_relevance_seconds=None,
            task_prompt_seconds=None,
            task_execution_seconds=None,
            primitive_dispatch_seconds=None,
            action_history_summary_seconds=None,
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
    relevance_decision: types.RelevantMemoryDecision | None,
    relevant_memories: RetrievedMemoryContext | None,
    selected_memory_contexts: list[types.TaskPromptSelectedMemoryContext] | None,
    task_prompt: types.TaskPromptDecision | None,
    task_execution: types.TaskExecutionResult | None,
    primitive_dispatch: PrimitiveDispatchResult | None,
    action_history_summary: str | None,
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
        relevance_decision=relevance_decision,
        relevant_memories=relevant_memories,
        selected_memory_contexts=selected_memory_contexts,
        task_prompt=task_prompt,
        task_execution=task_execution,
        primitive_dispatch=primitive_dispatch,
        action_history_summary=action_history_summary,
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
            post_vad_memory_relevance_seconds=timings[
                "post_vad_memory_relevance_seconds"
            ],
            post_vad_task_prompt_seconds=timings["post_vad_task_prompt_seconds"],
            post_vad_task_execution_seconds=timings[
                "post_vad_task_execution_seconds"
            ],
            post_vad_primitive_dispatch_seconds=timings[
                "post_vad_primitive_dispatch_seconds"
            ],
            post_vad_action_history_summary_seconds=timings[
                "post_vad_action_history_summary_seconds"
            ],
            transcription_seconds=timings["transcription_seconds"],
            task_choice_seconds=timings["task_choice_seconds"],
            memory_search_seconds=timings["memory_search_seconds"],
            search_depth_seconds=timings["search_depth_seconds"],
            memory_retrieval_seconds=timings["memory_retrieval_seconds"],
            memory_relevance_seconds=timings["memory_relevance_seconds"],
            task_prompt_seconds=timings["task_prompt_seconds"],
            task_execution_seconds=timings["task_execution_seconds"],
            primitive_dispatch_seconds=timings["primitive_dispatch_seconds"],
            action_history_summary_seconds=timings[
                "action_history_summary_seconds"
            ],
        ),
    )
