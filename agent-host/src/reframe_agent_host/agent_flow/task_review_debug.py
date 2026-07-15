from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping

from baml_sdk import task as baml_task
from reframe_agent_host.agent_flow.prompt_layer_debug import PromptLayerDebugSession


async def dump_task_reviews(debug: PromptLayerDebugSession, result) -> None:
    failures = {review.attempt_id: review for review in result.failure_reviews}
    order = 9
    for review in result.completion_reviews:
        inputs = {
            "completion_string": review.completion_string,
            "output_summary": review.output_summary,
        }
        await _write_prompt_layer(
            debug,
            order,
            "check_task_completion",
            inputs=inputs,
            result=review.completion,
            elapsed_seconds=_seconds(review.elapsed_ms),
            build_request=lambda inputs=inputs: (
                baml_task.CheckTaskCompletion__build_request_async(**inputs)
            ),
        )
        order += 1
        failure = failures.get(review.attempt_id)
        if failure is None:
            continue
        inputs = {
            "task_prompt": failure.task_prompt,
            "completion_string": failure.completion_string,
            "output_summary": failure.output_summary,
            "earlier_refusal_reply_text": failure.earlier_refusal_reply_text,
        }
        await _write_prompt_layer(
            debug,
            order,
            "write_validation_reply",
            inputs=inputs,
            result=failure.decision,
            elapsed_seconds=_seconds(failure.elapsed_ms),
            build_request=lambda inputs=inputs: (
                baml_task.WriteValidationReply__build_request_async(**inputs)
            ),
        )
        order += 1


async def _write_prompt_layer(
    debug: PromptLayerDebugSession,
    order: int,
    name: str,
    *,
    inputs: Mapping[str, Any],
    result: Any,
    elapsed_seconds: float,
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


def _seconds(milliseconds) -> float:
    return float(milliseconds) / 1000.0
