from __future__ import annotations

from dataclasses import dataclass

import baml_sdk as baml
import baml_sdk as types
from reframe_agent_host.agent_flow.baml_clients import client_kwargs, provider_client
from reframe_memory import MemoryDatabase, open_memory_database


@dataclass
class TaskExecutionPlanner:
    database: MemoryDatabase | None = None

    async def execute_task(
        self,
        selected_task_id: str,
        full_task_prompt: str,
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

        client, _client_name = provider_client(provider)
        return await baml.ExecuteTask_async(
            full_task_prompt=full_task_prompt,
            **client_kwargs(client),
        )

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
    return await baml.ExecuteTask_async(full_task_prompt=full_task_prompt)
