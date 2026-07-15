from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from reframe_memory.ids import memory_node_record_id
from reframe_memory.models import (
    Conversation,
    ConversationMessage,
    ConversationMessageNode,
    ConversationNode,
)
from reframe_memory.records import memory_node_from_record
from reframe_memory.query_results import first_record as _first_record
from reframe_memory.query_results import records as _records
from reframe_memory.search import (
    MemoryNodeSearch,
    StringSearch,
    TagSearch,
    build_memory_node_where,
)
from reframe_memory.sessions import SESSIONS_ROOT_ID

if TYPE_CHECKING:
    from reframe_memory.database import MemoryDatabase


CONVERSATIONS_ROOT_ID = "memory_root:conversations"
CONVERSATIONS_ROOT_NAME = "Conversations"
CONVERSATIONS_ROOT_DESCRIPTION = (
    "Nodes connected from this root are conversations grouped under sessions."
)


@dataclass(frozen=True)
class ConversationSearch:
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
    ) -> "ConversationSearch":
        return cls(
            tags=tags or TagSearch(),
            strings=strings or StringSearch(),
            names=tuple(names),
        )


@dataclass
class ConversationMemory:
    database: MemoryDatabase

    async def ensure_root(self) -> None:
        await self.database.query(
            f"""
            UPSERT {CONVERSATIONS_ROOT_ID} SET
                name = $name,
                description = $description;
            """,
            {
                "name": CONVERSATIONS_ROOT_NAME,
                "description": CONVERSATIONS_ROOT_DESCRIPTION,
            },
        )

    async def create(
        self,
        session_id: str,
        conversation: Conversation,
        tags: Sequence[str] = (),
    ) -> ConversationNode:
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
                "content": asdict(conversation),
            },
        )
        node = _first_record(result)
        await self.database.query(
            f"RELATE {CONVERSATIONS_ROOT_ID}->contains->$node_id;",
            {"node_id": node["id"]},
        )
        await self.database.query(
            f"RELATE {session_record_id}->has_conversation->$node_id;",
            {"node_id": node["id"]},
        )
        return conversation_node_from_record(node)

    async def add_message(
        self,
        conversation_id: str,
        message: ConversationMessage,
        tags: Sequence[str] = (),
        position: int | None = None,
    ) -> ConversationMessageNode:
        conversation_record_id = await self._ensure_conversation(conversation_id)
        message_position = (
            position
            if position is not None
            else await self._next_message_position(conversation_record_id)
        )
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
                "content": asdict(message),
            },
        )
        node = _first_record(result)
        await self.database.query(
            f"""
            RELATE {conversation_record_id}->has_message->$node_id
            SET position = $position;
            """,
            {"node_id": node["id"], "position": message_position},
        )
        await self.database.query(
            f"UPDATE {conversation_record_id} SET updated_at = time::now();",
        )
        return conversation_message_node_from_record(node)

    async def messages_for(
        self,
        conversation_id: str,
        *,
        mark_read: bool = True,
    ) -> list[ConversationMessageNode]:
        conversation_record_id = memory_node_record_id(conversation_id)
        relation_result = await self.database.query(
            f"""
            SELECT out, position FROM has_message
            WHERE in = {conversation_record_id}
            ORDER BY position ASC;
            """,
        )
        messages: list[ConversationMessageNode] = []
        for relation in _records(relation_result):
            message_id = memory_node_record_id(str(relation["out"]))
            message_result = await self.database.query(f"SELECT * FROM {message_id};")
            records = _records(message_result)
            if records:
                touched = (
                    await self.database.mark_records_read(records)
                    if mark_read
                    else records
                )
                messages.append(conversation_message_node_from_record(touched[0]))
        return messages

    async def search(
        self,
        search: ConversationSearch | None = None,
        *,
        mark_read: bool = True,
    ) -> list[ConversationNode]:
        parts = build_memory_node_where(_memory_search_from_conversation_search(search))
        result = await self.database.query(
            f"""
            SELECT * FROM {CONVERSATIONS_ROOT_ID}->contains->memory_node
            {parts.where_sql}
            ORDER BY updated_at DESC, created_at DESC;
            """,
            parts.variables,
        )
        records = _records(result)
        if mark_read:
            records = await self.database.mark_records_read(records)
        return [conversation_node_from_record(record) for record in records]

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

    async def _ensure_conversation(self, conversation_id: str) -> str:
        conversation_record_id = memory_node_record_id(conversation_id)
        result = await self.database.query(
            f"""
            SELECT id FROM {CONVERSATIONS_ROOT_ID}->contains->memory_node
            WHERE id = {conversation_record_id}
            LIMIT 1;
            """,
        )
        if not _records(result):
            msg = f"conversation does not exist under Conversations root: {conversation_id}"
            raise ValueError(msg)

        return conversation_record_id

    async def _next_message_position(self, conversation_record_id: str) -> int:
        result = await self.database.query(
            f"""
            SELECT position FROM has_message
            WHERE in = {conversation_record_id}
            ORDER BY position DESC
            LIMIT 1;
            """,
        )
        records = _records(result)
        if not records:
            return 0

        return int(records[0]["position"]) + 1


def _memory_search_from_conversation_search(
    search: ConversationSearch | None,
) -> MemoryNodeSearch | None:
    if search is None:
        return None

    return MemoryNodeSearch(
        tags=search.tags,
        strings=search.strings,
        string_fields=("name",),
        content_contains={"name": search.names},
    )


def conversation_node_from_record(record: Mapping[str, Any]) -> ConversationNode:
    return memory_node_from_record(record, _parse_conversation)


def conversation_message_node_from_record(
    record: Mapping[str, Any],
) -> ConversationMessageNode:
    return memory_node_from_record(record, _parse_conversation_message)


def _parse_conversation(content: Mapping[str, Any]) -> Conversation:
    return Conversation(name=str(content["name"]))


def _parse_conversation_message(content: Mapping[str, Any]) -> ConversationMessage:
    role = str(content["role"])
    if role not in (
        "human",
        "agent",
        "agent_thought",
        "agent_reply_interrupted",
        "validation_reply",
    ):
        msg = (
            "conversation message role must be human, agent, agent_thought, "
            "agent_reply_interrupted, or validation_reply, "
            f"got {role!r}"
        )
        raise ValueError(msg)

    return ConversationMessage(role=role, content=str(content["content"]))
