from __future__ import annotations

from dataclasses import dataclass
import time

import baml_sdk as baml
import baml_sdk as types
from reframe_agent_host.agent_flow.baml_clients import client_kwargs, provider_client
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
    ) -> types.TaskExecutionResult:
        database = await self._get_database()
        task = await database.tasks.get(selected_task_id)
        if task is None:
            msg = f"selected task does not exist: {selected_task_id}"
            raise ValueError(msg)

        provider = await database.providers.get(task.content.provider_id)
        if provider is None:
            msg = f"task provider does not exist: {task.content.provider_id}"
            raise ValueError(msg)

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
            request = await baml.PerformTask__build_request_async(
                full_task_prompt=full_task_prompt,
                **kwargs,
            )
        if debug_dump is not None and request is not None:
            debug_dump.record_request(request)

        started_at = time.perf_counter()
        try:
            result = await baml.PerformTask_async(
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

    async def close(self) -> None:
        if self.database is not None:
            await self.database.close()
            self.database = None

    async def _get_database(self) -> MemoryDatabase:
        if self.database is None:
            self.database = await open_memory_database()
            await self.database.apply_schema()
            await self.database.ensure_roots()
        return self.database


async def execute_task_with_default_client(
    full_task_prompt: str,
) -> types.TaskExecutionResult:
    return await baml.PerformTask_async(
        full_task_prompt=full_task_prompt,
    )
