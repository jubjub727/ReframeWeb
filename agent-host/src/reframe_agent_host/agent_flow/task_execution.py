from __future__ import annotations

from dataclasses import dataclass
import time

from baml_sdk import task_execution as baml_task_execution
from reframe_agent_host.agent_flow.provider_clients import client_kwargs, provider_client
from reframe_agent_host.magic_providers import (
    MAGIC_DO_NOTHING_CLIENT_NAME,
    is_magic_do_nothing_provider,
)
from reframe_agent_host.agent_flow.prompt_layer_debug import (
    PromptLayerDebugSession,
)
from reframe_agent_host.agent_flow.task_execution_debug import (
    TaskExecutionDebugDump,
)
from reframe_memory import MemoryDatabase, open_memory_database


@dataclass
class TaskExecutionPlanner:
    database: MemoryDatabase | None = None

    async def execute_task(
        self,
        selected_task_id: str,
        full_task_prompt: str,
        prompt_layer_debug: PromptLayerDebugSession | None = None,
    ) -> baml_task_execution.TaskExecutionResult:
        database = await self._get_database()
        task = await database.tasks.get(selected_task_id)
        if task is None:
            msg = f"selected task does not exist: {selected_task_id}"
            raise ValueError(msg)

        provider = await database.providers.get(task.content.provider_id)
        if provider is None:
            msg = f"task provider does not exist: {task.content.provider_id}"
            raise ValueError(msg)

        if is_magic_do_nothing_provider(provider):
            return self._execute_magic_do_nothing(
                task=task,
                provider=provider,
                full_task_prompt=full_task_prompt,
                prompt_layer_debug=prompt_layer_debug,
            )

        client, client_name = provider_client(provider)
        kwargs = client_kwargs(client)
        debug_dump = TaskExecutionDebugDump.begin(
            selected_task=task,
            provider=provider,
            client_name=client_name,
            full_task_prompt=full_task_prompt,
        )
        request = None
        if debug_dump is not None or prompt_layer_debug is not None:
            request = await baml_task_execution.PerformTask__build_request_async(
                full_task_prompt=full_task_prompt,
                **kwargs,
            )
        if debug_dump is not None and request is not None:
            debug_dump.record_request(request)

        started_at = time.perf_counter()
        try:
            result = await baml_task_execution.PerformTask_async(
                full_task_prompt=full_task_prompt,
                **kwargs,
            )
        except Exception as error:
            if debug_dump is not None:
                debug_dump.record_error(
                    elapsed_seconds=time.perf_counter() - started_at,
                    error=error,
                )
            if prompt_layer_debug is not None:
                prompt_layer_debug.write_layer(
                    order=7,
                    name="perform_task",
                    inputs={
                        "selected_task": task,
                        "provider": provider,
                        "client_name": client_name,
                        "full_task_prompt": full_task_prompt,
                    },
                    request=request,
                    elapsed_seconds=time.perf_counter() - started_at,
                    error=error,
                )
            raise

        if debug_dump is not None:
            debug_dump.record_result(
                elapsed_seconds=time.perf_counter() - started_at,
                result=result,
            )
        if prompt_layer_debug is not None:
            prompt_layer_debug.write_layer(
                order=7,
                name="perform_task",
                inputs={
                    "selected_task": task,
                    "provider": provider,
                    "client_name": client_name,
                    "full_task_prompt": full_task_prompt,
                },
                result=result,
                request=request,
                elapsed_seconds=time.perf_counter() - started_at,
            )
        return result

    def _execute_magic_do_nothing(
        self,
        *,
        task,
        provider,
        full_task_prompt: str,
        prompt_layer_debug: PromptLayerDebugSession | None,
    ) -> baml_task_execution.TaskExecutionResult:
        client_name = MAGIC_DO_NOTHING_CLIENT_NAME
        debug_dump = TaskExecutionDebugDump.begin(
            selected_task=task,
            provider=provider,
            client_name=client_name,
            full_task_prompt=full_task_prompt,
        )
        started_at = time.perf_counter()
        result = baml_task_execution.TaskExecutionResult(returns=[])
        elapsed_seconds = time.perf_counter() - started_at
        if debug_dump is not None:
            debug_dump.record_result(
                elapsed_seconds=elapsed_seconds,
                result=result,
            )
        if prompt_layer_debug is not None:
            prompt_layer_debug.write_layer(
                order=7,
                name="perform_task",
                inputs={
                    "selected_task": task,
                    "provider": provider,
                    "client_name": client_name,
                    "full_task_prompt": full_task_prompt,
                },
                result=result,
                request=None,
                elapsed_seconds=elapsed_seconds,
            )
        return result

    async def close(self) -> None:
        if self.database is not None:
            await self.database.close()
            self.database = None

    async def _get_database(self) -> MemoryDatabase:
        if self.database is None:
            self.database = await open_memory_database()
        return self.database


async def execute_task_with_default_client(
    full_task_prompt: str,
) -> baml_task_execution.TaskExecutionResult:
    return await baml_task_execution.PerformTask_async(
        full_task_prompt=full_task_prompt,
    )
