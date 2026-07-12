from __future__ import annotations

import time

from baml_sdk import context as baml_context
from reframe_agent_host.agent_flow.retrieved_memory_graph import (
    BamlRetrievedMemoryContext,
)
from reframe_agent_host.voice.turn_results import (
    transcribed_only_turn_result,
    transcribed_turn_result,
)
from reframe_agent_host.voice.turn_side_effects import TurnSideEffects
from reframe_agent_host.voice.capture_types import CaptureResult, VoiceTurnControl
from reframe_agent_host.voice.pipeline_config import (
    VoicePipelineConfig,
    VoicePipelineEventHandler,
)
from reframe_agent_host.voice.turn_data import VoiceTurnResult
from reframe_memory.retrieved_context import RetrievedMemoryContext


async def process_agent_turn(
    *,
    config: VoicePipelineConfig,
    turn_flow,
    side_effects: TurnSideEffects,
    capture: CaptureResult,
    conversation_mode: baml_context.ConversationMode,
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

    _emit(on_event, "turn-understanding", "understanding task and memory needs with BAML")
    understanding = await turn_flow.understand_prompt(routed_transcript)
    post_vad_understanding_seconds = time.perf_counter() - post_vad_started_at
    task_choice = understanding.task_choice
    selected_task = understanding.selected_task
    memory_search_hints = understanding.memory_search_hints
    search_depths = understanding.search_depths
    task_choice_seconds = _seconds_from_ms(understanding.timings.task_choice_ms)
    memory_search_seconds = _seconds_from_ms(understanding.timings.memory_search_ms)
    search_depth_seconds = _seconds_from_ms(understanding.timings.search_depth_ms)

    _emit(
        on_event,
        "task-chosen",
        f"selected: {selected_task.name} ({task_choice_seconds:.3f}s)",
    )
    _emit(
        on_event,
        "memory-search-hints",
        f"{memory_search_hints.model_dump(mode='json')} ({memory_search_seconds:.3f}s)",
    )
    _emit(
        on_event,
        "search-depths",
        f"{search_depths.model_dump(mode='json')} ({search_depth_seconds:.3f}s)",
    )
    await _checkpoint(turn_control)

    (
        retrieved_memories,
        memory_retrieval_seconds,
        post_vad_memory_retrieval_seconds,
    ) = await side_effects.retrieve_memories(
        memory_search_hints,
        search_depths,
        post_vad_started_at,
        on_event,
    )
    await _checkpoint(turn_control)

    _emit(on_event, "turn-continuation", "continuing with retrieved memories in BAML")
    continuation = await turn_flow.continue_prompt(
        routed_transcript,
        selected_task,
        retrieved_memories or RetrievedMemoryContext(),
    )
    post_vad_completion_seconds = time.perf_counter() - post_vad_started_at
    relevance_decision = continuation.relevance_decision
    relevant_memories = BamlRetrievedMemoryContext.from_graph(
        continuation.selected_memories
    )
    task_prompt = continuation.task_prompt
    memory_relevance_seconds = _seconds_from_ms(
        continuation.timings.memory_relevance_ms
    )
    task_prompt_seconds = _seconds_from_ms(continuation.timings.task_prompt_ms)
    _emit(
        on_event,
        "memory-relevance-decision",
        f"{relevance_decision.model_dump(mode='json')} ({memory_relevance_seconds:.3f}s)",
    )
    _emit(
        on_event,
        "task-prompt-generated",
        f"{len(task_prompt.full_task_prompt)} chars ({task_prompt_seconds:.3f}s)",
    )
    await _checkpoint(turn_control)

    task_execution, task_execution_seconds, post_vad_task_execution_seconds = (
        await side_effects.execute_task(
            task_choice, task_prompt, post_vad_started_at, on_event
        )
    )
    await _checkpoint(turn_control)
    primitive_dispatch, primitive_dispatch_seconds, post_vad_primitive_dispatch_seconds = (
        await side_effects.dispatch_primitives(
            task_execution, post_vad_started_at, on_event
        )
    )
    await _checkpoint(turn_control)
    (
        action_history_summary,
        action_history_summary_seconds,
        post_vad_action_history_summary_seconds,
    ) = await side_effects.summarize_action_history(
        primitive_dispatch, task_choice, post_vad_started_at, on_event
    )
    await _checkpoint(turn_control)
    task_completion, task_completion_seconds, post_vad_task_completion_seconds = (
        await side_effects.check_task_completion(
            selected_task, action_history_summary, post_vad_started_at, on_event
        )
    )
    await _checkpoint(turn_control)

    return transcribed_turn_result(
        config=config,
        conversation_mode=conversation_mode,
        capture=capture,
        transcript=transcript,
        trigger_detection=trigger_detection,
        routed_transcript=routed_transcript,
        task_choice=task_choice,
        memory_search_hints=memory_search_hints,
        search_depths=search_depths,
        retrieved_memories=retrieved_memories,
        relevance_decision=relevance_decision,
        relevant_memories=relevant_memories,
        selected_memory_contexts=continuation.selected_memory_contexts,
        task_prompt=task_prompt,
        task_execution=task_execution,
        primitive_dispatch=primitive_dispatch,
        action_history_summary=action_history_summary,
        task_completion=task_completion,
        timings={
            "model_prepare_seconds": model_prepare_seconds,
            "total_started_at": total_started_at,
            "post_vad_transcript_seconds": time.perf_counter() - post_vad_started_at,
            "post_vad_task_choice_seconds": post_vad_understanding_seconds,
            "post_vad_memory_search_seconds": post_vad_understanding_seconds,
            "post_vad_search_depth_seconds": post_vad_understanding_seconds,
            "post_vad_memory_retrieval_seconds": post_vad_memory_retrieval_seconds,
            "post_vad_memory_relevance_seconds": post_vad_completion_seconds,
            "post_vad_task_prompt_seconds": post_vad_completion_seconds,
            "post_vad_task_execution_seconds": post_vad_task_execution_seconds,
            "post_vad_primitive_dispatch_seconds": post_vad_primitive_dispatch_seconds,
            "post_vad_action_history_summary_seconds": post_vad_action_history_summary_seconds,
            "post_vad_task_completion_seconds": post_vad_task_completion_seconds,
            "transcription_seconds": transcription_seconds,
            "task_choice_seconds": task_choice_seconds,
            "memory_search_seconds": memory_search_seconds,
            "search_depth_seconds": search_depth_seconds,
            "memory_retrieval_seconds": memory_retrieval_seconds,
            "memory_relevance_seconds": memory_relevance_seconds,
            "task_prompt_seconds": task_prompt_seconds,
            "task_execution_seconds": task_execution_seconds,
            "primitive_dispatch_seconds": primitive_dispatch_seconds,
            "action_history_summary_seconds": action_history_summary_seconds,
            "task_completion_seconds": task_completion_seconds,
        },
    )


async def _checkpoint(turn_control: VoiceTurnControl | None) -> None:
    if turn_control is not None:
        await turn_control.checkpoint()


def _emit(
    on_event: VoicePipelineEventHandler | None,
    stage: str,
    message: str,
) -> None:
    if on_event is not None:
        on_event(stage, message)


def _seconds_from_ms(milliseconds) -> float:
    return float(milliseconds) / 1000.0
