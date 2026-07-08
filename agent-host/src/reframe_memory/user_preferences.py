from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from reframe_memory.models import UserPreferenceMemory, UserPreferenceMemoryNode
from reframe_memory.records import memory_node_from_record
from reframe_memory.search import (
    MemoryNodeSearch,
    StringSearch,
    TagSearch,
    build_memory_node_where,
)

if TYPE_CHECKING:
    from reframe_memory.database import MemoryDatabase


USER_PREFERENCES_ROOT_ID = "memory_root:user_preferences"
USER_PREFERENCES_ROOT_NAME = "User Preferences"
USER_PREFERENCES_ROOT_DESCRIPTION = (
    "Nodes connected from this root are durable global user preferences."
)


@dataclass(frozen=True)
class UserPreferenceMemorySearch:
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
    ) -> "UserPreferenceMemorySearch":
        return cls(
            tags=tags or TagSearch(),
            strings=strings or StringSearch(),
            titles=tuple(titles),
            descriptions=tuple(descriptions),
        )


@dataclass
class UserPreferenceMemoryStore:
    database: MemoryDatabase

    async def ensure_root(self) -> None:
        await self.database.query(
            f"""
            UPSERT {USER_PREFERENCES_ROOT_ID} SET
                name = $name,
                description = $description;
            """,
            {
                "name": USER_PREFERENCES_ROOT_NAME,
                "description": USER_PREFERENCES_ROOT_DESCRIPTION,
            },
        )

    async def create(
        self,
        memory: UserPreferenceMemory,
        tags: Sequence[str] = (),
    ) -> UserPreferenceMemoryNode:
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
            f"RELATE {USER_PREFERENCES_ROOT_ID}->contains->$node_id;",
            {"node_id": node["id"]},
        )
        return user_preference_memory_node_from_record(node)

    async def search(
        self,
        search: UserPreferenceMemorySearch | None = None,
        *,
        mark_read: bool = True,
    ) -> list[UserPreferenceMemoryNode]:
        parts = build_memory_node_where(_memory_search_from_user_preference_search(search))
        result = await self.database.query(
            f"""
            SELECT * FROM {USER_PREFERENCES_ROOT_ID}->contains->memory_node
            {parts.where_sql}
            ORDER BY updated_at DESC, created_at DESC;
            """,
            parts.variables,
        )
        records = _records(result)
        if mark_read:
            records = await self.database.mark_records_read(records)
        return [user_preference_memory_node_from_record(record) for record in records]


def _memory_search_from_user_preference_search(
    search: UserPreferenceMemorySearch | None,
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


def user_preference_memory_node_from_record(
    record: Mapping[str, Any],
) -> UserPreferenceMemoryNode:
    return memory_node_from_record(record, _parse_user_preference_memory)


def _parse_user_preference_memory(
    content: Mapping[str, Any],
) -> UserPreferenceMemory:
    return UserPreferenceMemory(
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
