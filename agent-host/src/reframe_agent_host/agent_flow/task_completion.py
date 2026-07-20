from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Mapping

from baml_sdk import task as baml_task
from reframe_agent_host.agent_flow.prompt_layer_debug import (
    PromptLayerDebugSession,
)


@dataclass
class TaskCompletionChecker:
    async def check(
        self,
        *,
        completion_string: str,
        output_summary: str,
        current_user_request: str = "",
        prompt_layer_debug: PromptLayerDebugSession | None = None,
    ) -> baml_task.CompletionResult:
        inputs = {
            "completion_string": completion_string,
            "output_summary": output_summary,
            "current_user_request": current_user_request,
        }
        request = None
        if prompt_layer_debug is not None:
            request = await baml_task.CheckTaskCompletion__build_request_async(**inputs)

        started_at = time.perf_counter()
        try:
            result = await baml_task.CheckTaskCompletion_async(**inputs)
        except Exception as error:
            if prompt_layer_debug is not None:
                _write_debug_layer(
                    prompt_layer_debug,
                    inputs=inputs,
                    request=request,
                    elapsed_seconds=time.perf_counter() - started_at,
                    error=error,
                )
            raise

        if prompt_layer_debug is not None:
            _write_debug_layer(
                prompt_layer_debug,
                inputs=inputs,
                request=request,
                result=result,
                elapsed_seconds=time.perf_counter() - started_at,
            )
        return result


def _write_debug_layer(
    prompt_layer_debug: PromptLayerDebugSession,
    *,
    inputs: Mapping[str, Any],
    request: Any = None,
    result: Any = None,
    elapsed_seconds: float | None = None,
    error: Exception | None = None,
) -> None:
    prompt_layer_debug.write_layer(
        order=9,
        name="check_task_completion",
        inputs=inputs,
        request=request,
        result=result,
        elapsed_seconds=elapsed_seconds,
        error=error,
    )
