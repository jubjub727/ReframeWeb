from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from reframe_memory.ids import memory_node_record_id
from reframe_memory.models import Provider, ProviderNode
from reframe_memory.records import memory_node_from_record
from reframe_memory.search import (
    MemoryNodeSearch,
    StringSearch,
    TagSearch,
    build_memory_node_where,
)

if TYPE_CHECKING:
    from reframe_memory.database import MemoryDatabase
    from reframe_memory.models import TaskNode


PROVIDERS_ROOT_ID = "memory_root:providers"
PROVIDERS_ROOT_NAME = "Providers"
PROVIDERS_ROOT_DESCRIPTION = (
    "Nodes connected from this root are model or agent providers. "
    "Each node content object is a Provider with name, description, and baml_surface."
)
PROVIDES_TASK_RELATION = "provides_task"


@dataclass(frozen=True)
class ProviderSearch:
    tags: TagSearch = TagSearch()
    strings: StringSearch = StringSearch()
    names: tuple[str, ...] = ()
    descriptions: tuple[str, ...] = ()
    baml_surfaces: tuple[str, ...] = ()

    @classmethod
    def build(
        cls,
        *,
        tags: TagSearch | None = None,
        strings: StringSearch | None = None,
        names: Sequence[str] = (),
        descriptions: Sequence[str] = (),
        baml_surfaces: Sequence[str] = (),
    ) -> "ProviderSearch":
        return cls(
            tags=tags or TagSearch(),
            strings=strings or StringSearch(),
            names=tuple(names),
            descriptions=tuple(descriptions),
            baml_surfaces=tuple(baml_surfaces),
        )


@dataclass
class ProviderMemory:
    database: MemoryDatabase

    async def ensure_root(self) -> None:
        await self.database.query(
            f"""
            UPSERT {PROVIDERS_ROOT_ID} SET
                name = $name,
                description = $description;
            """,
            {
                "name": PROVIDERS_ROOT_NAME,
                "description": PROVIDERS_ROOT_DESCRIPTION,
            },
        )

    async def create(
        self,
        provider: Provider,
        tags: Sequence[str] = (),
    ) -> ProviderNode:
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
                "content": asdict(provider),
            },
        )
        node = _first_record(result)
        await self.database.query(
            f"RELATE {PROVIDERS_ROOT_ID}->contains->$node_id;",
            {"node_id": node["id"]},
        )
        return _parse_provider_node(node)

    async def get(self, provider_id: str) -> ProviderNode | None:
        provider_record_id = memory_node_record_id(provider_id)
        result = await self.database.query(
            f"""
            SELECT * FROM {PROVIDERS_ROOT_ID}->contains->memory_node
            WHERE id = {provider_record_id}
            LIMIT 1;
            """,
        )
        records = _records(result)
        if not records:
            return None

        return _parse_provider_node(records[0])

    async def search(
        self,
        search: ProviderSearch | None = None,
    ) -> list[ProviderNode]:
        parts = build_memory_node_where(_memory_search_from_provider_search(search))
        result = await self.database.query(
            f"""
            SELECT * FROM {PROVIDERS_ROOT_ID}->contains->memory_node
            {parts.where_sql}
            ORDER BY updated_at DESC, created_at DESC;
            """,
            parts.variables,
        )
        return [_parse_provider_node(record) for record in _records(result)]

    async def tasks_for(self, provider_id: str) -> list[TaskNode]:
        from reframe_memory.tasks import task_node_from_record

        provider_record_id = memory_node_record_id(provider_id)
        result = await self.database.query(
            f"""
            SELECT * FROM {provider_record_id}->{PROVIDES_TASK_RELATION}->memory_node
            ORDER BY updated_at DESC, created_at DESC;
            """,
        )
        return [task_node_from_record(record) for record in _records(result)]


def _memory_search_from_provider_search(
    search: ProviderSearch | None,
) -> MemoryNodeSearch | None:
    if search is None:
        return None

    return MemoryNodeSearch(
        tags=search.tags,
        strings=search.strings,
        string_fields=("name", "description", "baml_surface"),
        content_contains={
            "name": search.names,
            "description": search.descriptions,
            "baml_surface": search.baml_surfaces,
        },
    )


def _parse_provider_node(record: Mapping[str, Any]) -> ProviderNode:
    return memory_node_from_record(record, _parse_provider)


def _parse_provider(content: Mapping[str, Any]) -> Provider:
    return Provider(
        name=str(content["name"]),
        description=str(content["description"]),
        baml_surface=str(content["baml_surface"]),
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
