from __future__ import annotations

import asyncio
import time

from baml_sdk import voice_turn as baml_voice_turn
from baml_sdk import turn_context as baml_turn_context
from reframe_agent_host.agent_flow.retrieved_memory_graph import (
    BamlRetrievedMemoryContext,
)
from reframe_agent_host.voice.capture_types import CaptureResult, VoiceTurnControl
from reframe_agent_host.voice.pipeline_config import (
    VoicePipelineConfig,
    VoicePipelineEventHandler,
)
from reframe_agent_host.voice.task_flow_host import VoiceTaskFlowHost
from reframe_agent_host.voice.turn_data import VoiceTurnResult
from reframe_agent_host.voice.turn_results import (
    no_action_turn_result,
    transcribed_only_turn_result,
    transcribed_turn_result,
)
from reframe_agent_host.voice.turn_side_effects import TurnSideEffects


async def process_agent_turn(
    *,
    config: VoicePipelineConfig,
    turn_flow,
    side_effects: TurnSideEffects,
    capture: CaptureResult,
    conversation_mode: baml_turn_context.ConversationMode,
    model_prepare_seconds: float,
    total_started_at: float,
    on_event: VoicePipelineEventHandler | None,
    turn_control: VoiceTurnControl | None,
    transcript,
    trigger_detection,
    routed_transcript: str,
    post_vad_started_at: float,
    transcription_seconds: float,
) -> VoiceTurnResult:
    if not config.task_choice_enabled or not routed_transcript:
        if not routed_transcript:
            _emit(on_event, "task-choice", "skipped empty transcript")
        return transcribed_only_turn_result(
            config=config,
            conversation_mode=conversation_mode,
            capture=capture,
            transcript=transcript,
            trigger_detection=trigger_detection,
            routed_transcript=routed_transcript,
            model_prepare_seconds=model_prepare_seconds,
            total_started_at=total_started_at,
            post_vad_transcript_seconds=time.perf_counter() - post_vad_started_at,
            transcription_seconds=transcription_seconds,
        )

    if turn_flow is None:
        raise RuntimeError("Voice prompt processing requires a BAML turn flow.")

    _emit(
        on_event,
        "turn-understanding",
        "running complete routed voice turn in BAML",
    )
    host = VoiceTaskFlowHost(
        current_user_request=routed_transcript,
        turn_flow=turn_flow,
        side_effects=side_effects,
        post_vad_started_at=post_vad_started_at,
        on_event=on_event,
        turn_control=turn_control,
        loop=asyncio.get_running_loop(),
    )
    result = await turn_flow.run_voice_turn(routed_transcript, host)

    if isinstance(result, baml_voice_turn.VoiceTaskNoActionResult):
        return no_action_turn_result(
            config=config,
            conversation_mode=conversation_mode,
            capture=capture,
            transcript=transcript,
            trigger_detection=trigger_detection,
            routed_transcript=routed_transcript,
            task_choice=result.task_choice,
            model_prepare_seconds=model_prepare_seconds,
            total_started_at=total_started_at,
            post_vad_transcript_seconds=time.perf_counter() - post_vad_started_at,
            post_vad_task_choice_seconds=time.perf_counter() - post_vad_started_at,
            transcription_seconds=transcription_seconds,
            task_choice_seconds=_seconds(result.task_choice_ms),
        )

    cycle = host.cycles[result.cycle_id]
    attempt = host.attempts[result.attempt_id]
    attempt.post_vad_task_completion_seconds = (
        time.perf_counter() - post_vad_started_at
    )
    if any(
        review.attempt_id == result.attempt_id
        for review in result.completion_reviews
    ):
        _emit(
            on_event,
            "task-completion-reviewed",
            f"{result.task_completion.value} "
            f"({_seconds(result.task_completion_ms):.3f}s)",
        )
    if turn_control is not None:
        await turn_control.checkpoint()
    understanding = result.understanding
    continuation = result.continuation

    return transcribed_turn_result(
        config=config,
        conversation_mode=conversation_mode,
        capture=capture,
        transcript=transcript,
        trigger_detection=trigger_detection,
        routed_transcript=routed_transcript,
        task_choice=understanding.task_choice,
        memory_search_hints=understanding.memory_search_hints,
        search_depths=understanding.search_depths,
        retrieved_memories=cycle.retrieved_memories,
        relevance_decision=continuation.relevance_decision,
        relevant_memories=BamlRetrievedMemoryContext.from_graph(
            continuation.selected_memories
        ),
        selected_memory_contexts=continuation.selected_memory_contexts,
        task_prompt=continuation.task_prompt,
        task_execution=attempt.task_execution,
        primitive_dispatch=attempt.primitive_dispatch,
        action_history_summary=attempt.output_summary,
        task_completion=result.task_completion,
        timings={
            "model_prepare_seconds": model_prepare_seconds,
            "total_started_at": total_started_at,
            "post_vad_transcript_seconds": time.perf_counter()
            - post_vad_started_at,
            "post_vad_task_choice_seconds": cycle.post_vad_understanding_seconds,
            "post_vad_memory_search_seconds": cycle.post_vad_understanding_seconds,
            "post_vad_search_depth_seconds": cycle.post_vad_understanding_seconds,
            "post_vad_memory_retrieval_seconds": (
                cycle.post_vad_memory_retrieval_seconds
            ),
            "post_vad_memory_relevance_seconds": cycle.post_vad_continuation_seconds,
            "post_vad_task_prompt_seconds": cycle.post_vad_continuation_seconds,
            "post_vad_task_execution_seconds": (
                attempt.post_vad_task_execution_seconds
            ),
            "post_vad_primitive_dispatch_seconds": (
                attempt.post_vad_primitive_dispatch_seconds
            ),
            "post_vad_action_history_summary_seconds": (
                attempt.post_vad_output_summary_seconds
            ),
            "post_vad_task_completion_seconds": (
                attempt.post_vad_task_completion_seconds
            ),
            "transcription_seconds": transcription_seconds,
            "task_choice_seconds": _seconds(understanding.timings.task_choice_ms),
            "memory_search_seconds": _seconds(
                understanding.timings.memory_search_ms
            ),
            "search_depth_seconds": _seconds(understanding.timings.search_depth_ms),
            "memory_retrieval_seconds": cycle.memory_retrieval_seconds,
            "memory_relevance_seconds": _seconds(
                continuation.timings.memory_relevance_ms
            ),
            "task_prompt_seconds": _seconds(continuation.timings.task_prompt_ms),
            "task_execution_seconds": attempt.task_execution_seconds,
            "primitive_dispatch_seconds": attempt.primitive_dispatch_seconds,
            "action_history_summary_seconds": attempt.output_summary_seconds,
            "task_completion_seconds": _seconds(result.task_completion_ms),
        },
    )


def _emit(on_event, stage: str, message: str) -> None:
    if on_event is not None:
        on_event(stage, message)


def _seconds(milliseconds) -> float:
    return float(milliseconds) / 1000.0
