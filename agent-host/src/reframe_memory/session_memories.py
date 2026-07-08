from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from reframe_memory.ids import memory_node_record_id
from reframe_memory.models import SessionMemory, SessionMemoryNode
from reframe_memory.records import memory_node_from_record
from reframe_memory.search import (
    MemoryNodeSearch,
    StringSearch,
    TagSearch,
    build_memory_node_where,
)
from reframe_memory.sessions import SESSIONS_ROOT_ID

if TYPE_CHECKING:
    from reframe_memory.database import MemoryDatabase


SESSION_MEMORIES_ROOT_ID = "memory_root:session_memories"
SESSION_MEMORIES_ROOT_NAME = "Session Memories"
SESSION_MEMORIES_ROOT_DESCRIPTION = (
    "Nodes connected from this root are memories scoped to a session."
)


@dataclass(frozen=True)
class SessionMemorySearch:
    tags: TagSearch = TagSearch()
    strings: StringSearch = StringSearch()
    titles: tuple[str, ...] = ()
    descriptions: tuple[str, ...] = ()

    @classmethod
    def build(
        cls,
        *,
        tags: TagSearch | None = None,
        strings: StringSearch | None = None,
        titles: Sequence[str] = (),
        descriptions: Sequence[str] = (),
    ) -> "SessionMemorySearch":
        return cls(
            tags=tags or TagSearch(),
            strings=strings or StringSearch(),
            titles=tuple(titles),
            descriptions=tuple(descriptions),
        )


@dataclass
class SessionMemoryStore:
    database: MemoryDatabase

    async def ensure_root(self) -> None:
        await self.database.query(
            f"""
            UPSERT {SESSION_MEMORIES_ROOT_ID} SET
                name = $name,
                description = $description;
            """,
            {
                "name": SESSION_MEMORIES_ROOT_NAME,
                "description": SESSION_MEMORIES_ROOT_DESCRIPTION,
            },
        )

    async def create(
        self,
        session_id: str,
        memory: SessionMemory,
        tags: Sequence[str] = (),
    ) -> SessionMemoryNode:
        session_record_id = await self._ensure_session(session_id)
        result = await self.database.query(
            """
            CREATE memory_node SET
                tags = $tags,
                content = $content,
                created_at = time::now(),
                updated_at = time::now(),
                read_at = NONE;
            """,
            {
                "tags": list(dict.fromkeys(tag.strip() for tag in tags if tag.strip())),
                "content": asdict(memory),
            },
        )
        node = _first_record(result)
        await self.database.query(
            f"RELATE {SESSION_MEMORIES_ROOT_ID}->contains->$node_id;",
            {"node_id": node["id"]},
        )
        await self.database.query(
            f"RELATE {session_record_id}->has_session_memory->$node_id;",
            {"node_id": node["id"]},
        )
        return session_memory_node_from_record(node)

    async def search(
        self,
        search: SessionMemorySearch | None = None,
        *,
        mark_read: bool = True,
    ) -> list[SessionMemoryNode]:
        parts = build_memory_node_where(_memory_search_from_session_memory_search(search))
        result = await self.database.query(
            f"""
            SELECT * FROM {SESSION_MEMORIES_ROOT_ID}->contains->memory_node
            {parts.where_sql}
            ORDER BY updated_at DESC, created_at DESC;
            """,
            parts.variables,
        )
        records = _records(result)
        if mark_read:
            records = await self.database.mark_records_read(records)
        return [session_memory_node_from_record(record) for record in records]

    async def for_session(
        self,
        session_id: str,
        *,
        mark_read: bool = True,
    ) -> list[SessionMemoryNode]:
        session_record_id = memory_node_record_id(session_id)
        result = await self.database.query(
            f"""
            SELECT * FROM {session_record_id}->has_session_memory->memory_node
            ORDER BY updated_at DESC, created_at DESC;
            """,
        )
        records = _records(result)
        if mark_read:
            records = await self.database.mark_records_read(records)
        return [session_memory_node_from_record(record) for record in records]

    async def _ensure_session(self, session_id: str) -> str:
        session_record_id = memory_node_record_id(session_id)
        result = await self.database.query(
            f"""
            SELECT id FROM {SESSIONS_ROOT_ID}->contains->memory_node
            WHERE id = {session_record_id}
            LIMIT 1;
            """,
        )
        if not _records(result):
            msg = f"session does not exist under Sessions root: {session_id}"
            raise ValueError(msg)

        return session_record_id


def _memory_search_from_session_memory_search(
    search: SessionMemorySearch | None,
) -> MemoryNodeSearch | None:
    if search is None:
        return None

    return MemoryNodeSearch(
        tags=search.tags,
        strings=search.strings,
        string_fields=("title", "description"),
        content_contains={
            "title": search.titles,
            "description": search.descriptions,
        },
    )


def session_memory_node_from_record(record: Mapping[str, Any]) -> SessionMemoryNode:
    return memory_node_from_record(record, _parse_session_memory)


def _parse_session_memory(content: Mapping[str, Any]) -> SessionMemory:
    return SessionMemory(
        title=str(content["title"]),
        description=str(content["description"]),
    )


def _records(result: Any) -> list[Mapping[str, Any]]:
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, Mapping)]


def _first_record(result: Any) -> Mapping[str, Any]:
    records = _records(result)
    if not records:
        raise ValueError("query did not return a memory node")
    return records[0]
