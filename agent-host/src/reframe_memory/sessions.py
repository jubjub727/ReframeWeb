from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from reframe_memory.ids import memory_node_record_id
from reframe_memory.models import Session, SessionNode
from reframe_memory.records import memory_node_from_record
from reframe_memory.search import (
    MemoryNodeSearch,
    StringSearch,
    TagSearch,
    build_memory_node_where,
)

if TYPE_CHECKING:
    from reframe_memory.database import MemoryDatabase
    from reframe_memory.models import ConversationNode, SessionMemoryNode


SESSIONS_ROOT_ID = "memory_root:sessions"
SESSIONS_ROOT_NAME = "Sessions"
SESSIONS_ROOT_DESCRIPTION = "Nodes connected from this root are user sessions."


@dataclass(frozen=True)
class SessionSearch:
    tags: TagSearch = TagSearch()
    strings: StringSearch = StringSearch()
    names: tuple[str, ...] = ()

    @classmethod
    def build(
        cls,
        *,
        tags: TagSearch | None = None,
        strings: StringSearch | None = None,
        names: Sequence[str] = (),
    ) -> "SessionSearch":
        return cls(
            tags=tags or TagSearch(),
            strings=strings or StringSearch(),
            names=tuple(names),
        )


@dataclass
class SessionStore:
    database: MemoryDatabase

    async def ensure_root(self) -> None:
        await self.database.query(
            f"""
            UPSERT {SESSIONS_ROOT_ID} SET
                name = $name,
                description = $description;
            """,
            {
                "name": SESSIONS_ROOT_NAME,
                "description": SESSIONS_ROOT_DESCRIPTION,
            },
        )

    async def create(self, session: Session, tags: Sequence[str] = ()) -> SessionNode:
        await self.ensure_root()
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
                "content": asdict(session),
            },
        )
        node = _first_record(result)
        await self.database.query(
            f"RELATE {SESSIONS_ROOT_ID}->contains->$node_id;",
            {"node_id": node["id"]},
        )
        return session_node_from_record(node)

    async def get(self, session_id: str) -> SessionNode | None:
        session_record_id = memory_node_record_id(session_id)
        result = await self.database.query(
            f"""
            SELECT * FROM {SESSIONS_ROOT_ID}->contains->memory_node
            WHERE id = {session_record_id}
            LIMIT 1;
            """,
        )
        records = _records(result)
        if not records:
            return None

        return session_node_from_record(records[0])

    async def search(self, search: SessionSearch | None = None) -> list[SessionNode]:
        parts = build_memory_node_where(_memory_search_from_session_search(search))
        result = await self.database.query(
            f"""
            SELECT * FROM {SESSIONS_ROOT_ID}->contains->memory_node
            {parts.where_sql}
            ORDER BY updated_at DESC, created_at DESC;
            """,
            parts.variables,
        )
        return [session_node_from_record(record) for record in _records(result)]

    async def conversations_for(self, session_id: str) -> list[ConversationNode]:
        from reframe_memory.conversations import conversation_node_from_record

        session_record_id = memory_node_record_id(session_id)
        result = await self.database.query(
            f"""
            SELECT * FROM {session_record_id}->has_conversation->memory_node
            ORDER BY updated_at DESC, created_at DESC;
            """,
        )
        return [conversation_node_from_record(record) for record in _records(result)]

    async def memories_for(self, session_id: str) -> list[SessionMemoryNode]:
        from reframe_memory.session_memories import session_memory_node_from_record

        session_record_id = memory_node_record_id(session_id)
        result = await self.database.query(
            f"""
            SELECT * FROM {session_record_id}->has_session_memory->memory_node
            ORDER BY updated_at DESC, created_at DESC;
            """,
        )
        return [session_memory_node_from_record(record) for record in _records(result)]


def _memory_search_from_session_search(
    search: SessionSearch | None,
) -> MemoryNodeSearch | None:
    if search is None:
        return None

    return MemoryNodeSearch(
        tags=search.tags,
        strings=search.strings,
        string_fields=("name",),
        content_contains={"name": search.names},
    )


def session_node_from_record(record: Mapping[str, Any]) -> SessionNode:
    return memory_node_from_record(record, _parse_session)


def _parse_session(content: Mapping[str, Any]) -> Session:
    return Session(name=str(content["name"]))


def _records(result: Any) -> list[Mapping[str, Any]]:
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, Mapping)]


def _first_record(result: Any) -> Mapping[str, Any]:
    records = _records(result)
    if not records:
        raise ValueError("query did not return a memory node")
    return records[0]
