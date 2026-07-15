from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Mapping

from baml_sdk import task as baml_task
from reframe_agent_host.agent_flow.provider_clients import (
    BamlClient,
    client_kwargs,
    provider_client,
)
from reframe_agent_host.agent_flow.prompt_layer_debug import (
    PromptLayerDebugSession,
)
from reframe_memory import MemoryDatabase, open_memory_database


@dataclass
class ActionHistorySummarizer:
    database: MemoryDatabase | None = None
    client_name: str | None = None
    _owns_database: bool = field(init=False)

    def __post_init__(self) -> None:
        self._owns_database = self.database is None

    async def summarize(
        self,
        task_history_id: str,
        selected_task_id: str | None = None,
        prompt_layer_debug: PromptLayerDebugSession | None = None,
    ) -> str:
        database = await self._get_database()
        recorded_action_history = await database.task_history.render(task_history_id)
        inputs = {"recorded_action_history": recorded_action_history}
        client, client_name = await self._summary_client(
            database,
            selected_task_id,
        )
        kwargs = client_kwargs(client)
        debug_inputs = {
            **inputs,
            "selected_task_id": selected_task_id,
            "client_name": client_name,
        }
        request = None
        if prompt_layer_debug is not None:
            request = await baml_task.SummariseActionHistory__build_request_async(
                **inputs,
                **kwargs,
            )

        started_at = time.perf_counter()
        try:
            result = await baml_task.SummariseActionHistory_async(
                **inputs,
                **kwargs,
            )
        except Exception as error:
            if prompt_layer_debug is not None:
                _write_debug_layer(
                    prompt_layer_debug,
                    inputs=debug_inputs,
                    request=request,
                    elapsed_seconds=time.perf_counter() - started_at,
                    error=error,
                )
            raise

        if prompt_layer_debug is not None:
            _write_debug_layer(
                prompt_layer_debug,
                inputs=debug_inputs,
                request=request,
                result=result,
                elapsed_seconds=time.perf_counter() - started_at,
            )
        return result

    async def close(self) -> None:
        if self.database is not None and self._owns_database:
            await self.database.close()
            self.database = None

    async def _get_database(self) -> MemoryDatabase:
        if self.database is None:
            self.database = await open_memory_database()
        return self.database

    async def _summary_client(
        self,
        database: MemoryDatabase,
        selected_task_id: str | None,
    ) -> tuple[BamlClient | str | None, str | None]:
        if self.client_name is not None:
            return self.client_name, self.client_name
        if selected_task_id is None:
            msg = "selected_task_id is required to use the task execution provider"
            raise ValueError(msg)

        task = await database.tasks.get(selected_task_id)
        if task is None:
            msg = f"selected task does not exist: {selected_task_id}"
            raise ValueError(msg)

        provider = await database.providers.get(task.content.provider_id)
        if provider is None:
            msg = f"task provider does not exist: {task.content.provider_id}"
            raise ValueError(msg)

        return provider_client(provider)


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
        order=8,
        name="summarise_action_history",
        inputs=inputs,
        request=request,
        result=result,
        elapsed_seconds=elapsed_seconds,
        error=error,
    )
