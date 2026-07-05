from __future__ import annotations

from dataclasses import dataclass

from reframe_agent_host.agent_flow.provider_clients import opencode_provider_client
from reframe_agent_host.baml_client import b, types
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

        client, _client_name = opencode_provider_client(provider)
        return await client.ExecuteTask(full_task_prompt=full_task_prompt)

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
    return await b.ExecuteTask(full_task_prompt=full_task_prompt)
