from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any

from surrealdb import AsyncSurreal

from reframe_memory.config import MemoryConfig
from reframe_memory.ids import memory_node_record_id


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

    async def mark_records_read(
        self,
        records: list[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        updated: list[Mapping[str, Any]] = []
        for record in records:
            record_id = memory_node_record_id(str(record["id"]))
            result = await self.query(
                f"UPDATE {record_id} SET read_at = time::now() RETURN AFTER;",
            )
            result_records = _records(result)
            updated.append(result_records[0] if result_records else record)
        return updated

    async def mark_record_ids_read(self, record_ids: list[str]) -> None:
        for record_id in dict.fromkeys(
            memory_node_record_id(record_id) for record_id in record_ids
        ):
            await self.query(
                f"UPDATE {record_id} SET read_at = time::now();",
            )

    async def apply_schema(self) -> None:
        from reframe_memory.schema import SCHEMA_STATEMENTS

        for statement in SCHEMA_STATEMENTS:
            await self.query(statement)

    async def ensure_roots(self) -> None:
        await self.providers.ensure_root()
        await self.tasks.ensure_root()
        await self.sessions.ensure_root()
        await self.conversations.ensure_root()
        await self.session_memories.ensure_root()
        await self.task_choice_memories.ensure_root()
        await self.conversation_evaluation_memories.ensure_root()
        await self.search_depth_memories.ensure_root()
        await self.relevance_memories.ensure_root()
        await self.task_prompt_memories.ensure_root()
        await self.user_preferences.ensure_root()

    @property
    def tasks(self) -> "TaskMemory":
        from reframe_memory.tasks import TaskMemory

        return TaskMemory(self)

    @property
    def providers(self) -> "ProviderMemory":
        from reframe_memory.providers import ProviderMemory

        return ProviderMemory(self)

    @property
    def sessions(self) -> "SessionStore":
        from reframe_memory.sessions import SessionStore

        return SessionStore(self)

    @property
    def conversations(self) -> "ConversationMemory":
        from reframe_memory.conversations import ConversationMemory

        return ConversationMemory(self)

    @property
    def session_memories(self) -> "SessionMemoryStore":
        from reframe_memory.session_memories import SessionMemoryStore

        return SessionMemoryStore(self)

    @property
    def task_choice_memories(self) -> "TaskChoiceMemoryStore":
        from reframe_memory.task_choice_memories import TaskChoiceMemoryStore

        return TaskChoiceMemoryStore(self)

    @property
    def conversation_evaluation_memories(self) -> "ConversationEvaluationMemoryStore":
        from reframe_memory.conversation_evaluation_memories import (
            ConversationEvaluationMemoryStore,
        )

        return ConversationEvaluationMemoryStore(self)

    @property
    def search_depth_memories(self) -> "SearchDepthMemoryStore":
        from reframe_memory.search_depth_memories import SearchDepthMemoryStore

        return SearchDepthMemoryStore(self)

    @property
    def relevance_memories(self) -> "RelevanceMemoryStore":
        from reframe_memory.relevance_memories import RelevanceMemoryStore

        return RelevanceMemoryStore(self)

    @property
    def task_prompt_memories(self) -> "TaskPromptMemoryStore":
        from reframe_memory.task_prompt_memories import TaskPromptMemoryStore

        return TaskPromptMemoryStore(self)

    @property
    def user_preferences(self) -> "UserPreferenceMemoryStore":
        from reframe_memory.user_preferences import UserPreferenceMemoryStore

        return UserPreferenceMemoryStore(self)


async def open_memory_database(config: MemoryConfig | None = None) -> MemoryDatabase:
    return await MemoryDatabase.open(config)


def _records(result: Any) -> list[Mapping[str, Any]]:
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, Mapping)]
