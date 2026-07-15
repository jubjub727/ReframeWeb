from __future__ import annotations

from reframe_agent_host.agent_flow.prompt_layer_debug import PromptLayerDebugSession
from reframe_agent_host.agent_flow.voice_prompt_debug import (
    dump_continuation_layers,
    dump_understanding_layers,
)


async def record_understanding_layers(
    debug: PromptLayerDebugSession,
    inputs,
    result,
    kwargs,
) -> None:
    debug.write_layer(
        order=0,
        name="understand_voice_prompt",
        inputs=inputs,
        result=result,
        elapsed_seconds=_seconds(
            result.timings.task_choice_ms
            + result.timings.memory_search_ms
            + result.timings.search_depth_ms
        ),
    )
    try:
        await dump_understanding_layers(debug, inputs, result, kwargs)
    except Exception:
        pass


async def record_continuation_layers(
    debug: PromptLayerDebugSession,
    context_inputs,
    selected_task,
    retrieved_memories,
    result,
    kwargs,
) -> None:
    inputs = {
        key: context_inputs[key]
        for key in (
            "current_user_request",
            "current_conversation",
            "session_memories",
            "user_preferences",
            "current_session_id",
            "relevance_memories",
            "task_prompt_memories",
            "machine_state",
        )
    }
    inputs.update(
        selected_task=selected_task,
        retrieved_memories=retrieved_memories,
    )
    debug.write_layer(
        order=4,
        name="continue_voice_prompt",
        inputs=inputs,
        result=result,
        elapsed_seconds=_seconds(
            result.timings.memory_relevance_ms + result.timings.task_prompt_ms
        ),
    )
    try:
        await dump_continuation_layers(debug, inputs, result, kwargs)
    except Exception:
        pass


def _seconds(milliseconds) -> float:
    return float(milliseconds) / 1000.0
