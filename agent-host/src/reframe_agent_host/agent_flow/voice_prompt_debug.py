from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping

from baml_sdk import memory as baml_memory
from baml_sdk import task as baml_task
from baml_sdk import voice_turn as baml_voice_turn
from reframe_agent_host.agent_flow.prompt_layer_debug import PromptLayerDebugSession


async def dump_understanding_layers(
    debug: PromptLayerDebugSession,
    inputs: Mapping[str, Any],
    result: baml_voice_turn.VoicePromptUnderstanding,
    kwargs: dict[str, Any],
) -> None:
    choose_task_inputs = {
        key: inputs[key]
        for key in (
            "current_user_request",
            "current_conversation",
            "session_memories",
            "user_preferences",
            "available_tasks",
            "task_choice_memories",
            "machine_state",
        )
    }
    await _write_prompt_layer(
        debug,
        1,
        "choose_task",
        inputs=choose_task_inputs,
        result=result.task_choice,
        elapsed_seconds=_seconds_from_ms(result.timings.task_choice_ms),
        build_request=lambda: baml_task.ChooseTask__build_request_async(
            **choose_task_inputs, **kwargs
        ),
    )

    memory_search_inputs = {
        "current_user_request": inputs["current_user_request"],
        "current_conversation": inputs["current_conversation"],
        "session_memories": inputs["session_memories"],
        "selected_task": result.selected_task,
        "conversation_evaluation_memories": inputs[
            "conversation_evaluation_memories"
        ],
        "machine_state": inputs["machine_state"],
    }
    await _write_prompt_layer(
        debug,
        2,
        "choose_memory_search",
        inputs=memory_search_inputs,
        result=result.memory_search_hints,
        elapsed_seconds=_seconds_from_ms(result.timings.memory_search_ms),
        build_request=lambda: baml_memory.ChooseMemorySearch__build_request_async(
            **memory_search_inputs, **kwargs
        ),
    )

    search_depth_inputs = {
        "current_timestamp": inputs["current_timestamp"],
        "current_user_request": inputs["current_user_request"],
        "current_conversation": inputs["current_conversation"],
        "session_memories": inputs["session_memories"],
        "selected_task": result.selected_task,
        "memory_search_hints": result.memory_search_hints,
        "search_domains": await baml_memory.SearchDomains_async(),
        "search_depth_memories": inputs["search_depth_memories"],
        "machine_state": inputs["machine_state"],
    }
    await _write_prompt_layer(
        debug,
        3,
        "choose_memory_search_depths",
        inputs=search_depth_inputs,
        result=result.search_depths,
        elapsed_seconds=_seconds_from_ms(result.timings.search_depth_ms),
        build_request=lambda: baml_memory.ChooseMemorySearchDepths__build_request_async(
            **search_depth_inputs, **kwargs
        ),
    )


async def dump_continuation_layers(
    debug: PromptLayerDebugSession,
    inputs: Mapping[str, Any],
    result: baml_voice_turn.VoicePromptContinuation,
    kwargs: dict[str, Any],
) -> None:
    candidate_memories = await baml_memory.Candidates_async(
        inputs["retrieved_memories"],
        inputs["current_session_id"],
        inputs["user_preferences"],
    )
    relevance_inputs = {
        "current_user_request": inputs["current_user_request"],
        "current_conversation": inputs["current_conversation"],
        "session_memories": inputs["session_memories"],
        "selected_task": inputs["selected_task"],
        "candidate_memories": candidate_memories,
        "relevance_memories": inputs["relevance_memories"],
        "machine_state": inputs["machine_state"],
    }
    await _write_prompt_layer(
        debug,
        5,
        "select_relevant_memories",
        inputs=relevance_inputs,
        result=result.relevance_decision,
        elapsed_seconds=_seconds_from_ms(result.timings.memory_relevance_ms),
        build_request=lambda: baml_memory.SelectRelevantMemories__build_request_async(
            **relevance_inputs, **kwargs
        ),
    )

    composition = task_prompt_composition(result.task_prompt)
    composition_inputs = {
        "current_user_request": inputs["current_user_request"],
        "current_conversation": inputs["current_conversation"],
        "session_memories": inputs["session_memories"],
        "selected_task": inputs["selected_task"],
        "selected_memories": result.selected_memory_contexts,
        "task_prompt_memories": inputs["task_prompt_memories"],
        "machine_state": inputs["machine_state"],
    }
    await _write_prompt_layer(
        debug,
        6,
        "compose_task_input",
        inputs=composition_inputs,
        result=composition,
        elapsed_seconds=_seconds_from_ms(result.timings.task_prompt_ms),
        build_request=lambda: baml_task.ComposeTaskInput__build_request_async(
            **composition_inputs, **kwargs
        ),
    )


async def _write_prompt_layer(
    debug: PromptLayerDebugSession,
    order: int,
    name: str,
    *,
    inputs: Mapping[str, Any],
    result: Any,
    elapsed_seconds: float | None,
    build_request: Callable[[], Awaitable[Any]],
) -> None:
    debug_inputs = inputs
    try:
        request = await build_request()
    except Exception as error:
        request = None
        debug_inputs = {
            **inputs,
            "_debug_request_error": {
                "type": type(error).__name__,
                "message": str(error),
            },
        }
    debug.write_layer(
        order=order,
        name=name,
        inputs=debug_inputs,
        result=result,
        request=request,
        elapsed_seconds=elapsed_seconds,
    )


def task_prompt_composition(
    decision: baml_task.TaskPromptDecision,
) -> baml_task.TaskPromptComposition:
    marker = "\n\nInput:\n"
    _task_prompt, separator, task_input = decision.full_task_prompt.partition(marker)
    return baml_task.TaskPromptComposition(
        task_input=task_input if separator else decision.full_task_prompt,
        candidate_memory=decision.candidate_memory,
    )


def _seconds_from_ms(milliseconds) -> float:
    return float(milliseconds) / 1000.0
