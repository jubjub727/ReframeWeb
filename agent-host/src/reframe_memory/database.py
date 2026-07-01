from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from surrealdb import AsyncSurreal

from reframe_memory.config import MemoryConfig


@dataclass
class MemoryDatabase:
    config: MemoryConfig
    client: Any

    @classmethod
    async def open(cls, config: MemoryConfig | None = None) -> "MemoryDatabase":
        resolved = config or MemoryConfig.from_env()
        client = AsyncSurreal(resolved.url)
        await client.connect()
        await client.use(resolved.namespace, resolved.database)
        return cls(config=resolved, client=client)

    async def close(self) -> None:
        await self.client.close()

    async def query(self, statement: str, variables: dict[str, Any] | None = None) -> Any:
        return await self.client.query(statement, variables)

    async def apply_schema(self) -> None:
        from reframe_memory.schema import SCHEMA_STATEMENTS

        for statement in SCHEMA_STATEMENTS:
            await self.query(statement)

    @property
    def tasks(self) -> "TaskMemory":
        from reframe_memory.tasks import TaskMemory

        return TaskMemory(self)


async def open_memory_database(config: MemoryConfig | None = None) -> MemoryDatabase:
    return await MemoryDatabase.open(config)
