from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Event, Lock, Thread
from typing import Any, Awaitable

from surrealdb import AsyncSurreal

from reframe_memory.config import MemoryConfig
from reframe_memory.ids import memory_node_record_id
from reframe_memory.query_results import records as _records


@dataclass
class MemoryDatabase:
    config: MemoryConfig
    client: Any

    @classmethod
    async def open(cls, config: MemoryConfig | None = None) -> "MemoryDatabase":
        resolved = config or MemoryConfig.from_env()
        if _uses_embedded_surrealkv(resolved):
            return cls(config=resolved, client=_surrealkv_client(resolved))

        async def connect_client() -> AsyncSurreal:
            client = AsyncSurreal(resolved.url)
            await client.connect()
            await client.use(resolved.namespace, resolved.database)
            return client

        return cls(config=resolved, client=await connect_client())

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
        from reframe_memory.context_memories import TaskChoiceMemoryStore

        return TaskChoiceMemoryStore(self)

    @property
    def conversation_evaluation_memories(self) -> "ConversationEvaluationMemoryStore":
        from reframe_memory.context_memories import (
            ConversationEvaluationMemoryStore,
        )

        return ConversationEvaluationMemoryStore(self)

    @property
    def search_depth_memories(self) -> "SearchDepthMemoryStore":
        from reframe_memory.context_memories import SearchDepthMemoryStore

        return SearchDepthMemoryStore(self)

    @property
    def relevance_memories(self) -> "RelevanceMemoryStore":
        from reframe_memory.context_memories import RelevanceMemoryStore

        return RelevanceMemoryStore(self)

    @property
    def task_prompt_memories(self) -> "TaskPromptMemoryStore":
        from reframe_memory.context_memories import TaskPromptMemoryStore

        return TaskPromptMemoryStore(self)

    @property
    def user_preferences(self) -> "UserPreferenceMemoryStore":
        from reframe_memory.context_memories import UserPreferenceMemoryStore

        return UserPreferenceMemoryStore(self)

    @property
    def task_history(self) -> "TaskHistoryStore":
        from reframe_memory.task_history import TaskHistoryStore

        return TaskHistoryStore(self)


async def open_memory_database(config: MemoryConfig | None = None) -> MemoryDatabase:
    return await MemoryDatabase.open(config)


_SURREALKV_WORKERS: dict[MemoryConfig, "_SurrealKvWorker"] = {}
_SURREALKV_WORKERS_LOCK = Lock()


def _uses_embedded_surrealkv(config: MemoryConfig) -> bool:
    return config.url.lower().startswith("surrealkv://")


def _surrealkv_client(config: MemoryConfig) -> "_QueuedSurrealKvClient":
    with _SURREALKV_WORKERS_LOCK:
        worker = _SURREALKV_WORKERS.get(config)
        if worker is None:
            worker = _SurrealKvWorker(config)
            _SURREALKV_WORKERS[config] = worker
    return _QueuedSurrealKvClient(worker)


@dataclass(frozen=True)
class _QueuedSurrealKvClient:
    worker: "_SurrealKvWorker"

    async def query(
        self,
        statement: str,
        variables: dict[str, Any] | None = None,
    ) -> Any:
        return await self.worker.query(statement, variables)

    async def close(self) -> None:
        return None


class _SurrealKvWorker:
    def __init__(self, config: MemoryConfig) -> None:
        self._config = config
        self._ready = Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._operation_lock: asyncio.Lock | None = None
        self._client: AsyncSurreal | None = None
        self._thread = Thread(
            target=self._run_loop,
            name="reframe-memory-surrealkv",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait()

    async def query(
        self,
        statement: str,
        variables: dict[str, Any] | None = None,
    ) -> Any:
        return await self._submit(self._query(statement, variables))

    async def _submit(self, operation: Awaitable[Any]) -> Any:
        if self._loop is None:
            raise RuntimeError("SurrealKV worker loop is not ready")
        future = asyncio.run_coroutine_threadsafe(operation, self._loop)
        return await asyncio.wrap_future(future)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        self._operation_lock = asyncio.Lock()
        self._ready.set()
        loop.run_forever()

    async def _query(
        self,
        statement: str,
        variables: dict[str, Any] | None,
    ) -> Any:
        if self._operation_lock is None:
            raise RuntimeError("SurrealKV worker operation queue is not ready")
        async with self._operation_lock:
            client = await self._connected_client()
            return await client.query(statement, variables)

    async def _connected_client(self) -> AsyncSurreal:
        if self._client is not None:
            return self._client

        client = AsyncSurreal(self._config.url)
        await client.connect()
        await client.use(self._config.namespace, self._config.database)
        self._client = client
        return client
