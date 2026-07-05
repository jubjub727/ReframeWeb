from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from reframe_memory.models import RelevanceMemory, RelevanceMemoryNode
from reframe_memory.records import memory_node_from_record
from reframe_memory.search import (
    MemoryNodeSearch,
    StringSearch,
    TagSearch,
    build_memory_node_where,
)

if TYPE_CHECKING:
    from reframe_memory.database import MemoryDatabase


RELEVANCE_MEMORIES_ROOT_ID = "memory_root:relevance_memories"
RELEVANCE_MEMORIES_ROOT_NAME = "Relevance Memories"
RELEVANCE_MEMORIES_ROOT_DESCRIPTION = (
    "Nodes connected from this root are memories for the relevance-filter "
    "prompt step."
)


@dataclass(frozen=True)
class RelevanceMemorySearch:
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
    ) -> "RelevanceMemorySearch":
        return cls(
            tags=tags or TagSearch(),
            strings=strings or StringSearch(),
            titles=tuple(titles),
            descriptions=tuple(descriptions),
        )


@dataclass
class RelevanceMemoryStore:
    database: MemoryDatabase

    async def ensure_root(self) -> None:
        await self.database.query(
            f"""
            UPSERT {RELEVANCE_MEMORIES_ROOT_ID} SET
                name = $name,
                description = $description;
            """,
            {
                "name": RELEVANCE_MEMORIES_ROOT_NAME,
                "description": RELEVANCE_MEMORIES_ROOT_DESCRIPTION,
            },
        )

    async def create(
        self,
        memory: RelevanceMemory,
        tags: Sequence[str] = (),
    ) -> RelevanceMemoryNode:
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
                "content": asdict(memory),
            },
        )
        node = _first_record(result)
        await self.database.query(
            f"RELATE {RELEVANCE_MEMORIES_ROOT_ID}->contains->$node_id;",
            {"node_id": node["id"]},
        )
        return relevance_memory_node_from_record(node)

    async def search(
        self,
        search: RelevanceMemorySearch | None = None,
    ) -> list[RelevanceMemoryNode]:
        parts = build_memory_node_where(_memory_search_from_relevance_memory_search(search))
        result = await self.database.query(
            f"""
            SELECT * FROM {RELEVANCE_MEMORIES_ROOT_ID}->contains->memory_node
            {parts.where_sql}
            ORDER BY updated_at DESC, created_at DESC;
            """,
            parts.variables,
        )
        return [relevance_memory_node_from_record(record) for record in _records(result)]


def _memory_search_from_relevance_memory_search(
    search: RelevanceMemorySearch | None,
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


def relevance_memory_node_from_record(
    record: Mapping[str, Any],
) -> RelevanceMemoryNode:
    return memory_node_from_record(record, _parse_relevance_memory)


def _parse_relevance_memory(content: Mapping[str, Any]) -> RelevanceMemory:
    return RelevanceMemory(
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
