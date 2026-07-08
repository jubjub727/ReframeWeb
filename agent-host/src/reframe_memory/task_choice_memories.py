from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from reframe_memory.models import TaskChoiceMemory, TaskChoiceMemoryNode
from reframe_memory.records import memory_node_from_record
from reframe_memory.search import (
    MemoryNodeSearch,
    StringSearch,
    TagSearch,
    build_memory_node_where,
)

if TYPE_CHECKING:
    from reframe_memory.database import MemoryDatabase


TASK_CHOICE_MEMORIES_ROOT_ID = "memory_root:task_choice_memories"
TASK_CHOICE_MEMORIES_ROOT_NAME = "Task Choice Memories"
TASK_CHOICE_MEMORIES_ROOT_DESCRIPTION = (
    "Nodes connected from this root are memories for the task-choice prompt step."
)


@dataclass(frozen=True)
class TaskChoiceMemorySearch:
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
    ) -> "TaskChoiceMemorySearch":
        return cls(
            tags=tags or TagSearch(),
            strings=strings or StringSearch(),
            titles=tuple(titles),
            descriptions=tuple(descriptions),
        )


@dataclass
class TaskChoiceMemoryStore:
    database: MemoryDatabase

    async def ensure_root(self) -> None:
        await self.database.query(
            f"""
            UPSERT {TASK_CHOICE_MEMORIES_ROOT_ID} SET
                name = $name,
                description = $description;
            """,
            {
                "name": TASK_CHOICE_MEMORIES_ROOT_NAME,
                "description": TASK_CHOICE_MEMORIES_ROOT_DESCRIPTION,
            },
        )

    async def create(
        self,
        memory: TaskChoiceMemory,
        tags: Sequence[str] = (),
    ) -> TaskChoiceMemoryNode:
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
            f"RELATE {TASK_CHOICE_MEMORIES_ROOT_ID}->contains->$node_id;",
            {"node_id": node["id"]},
        )
        return task_choice_memory_node_from_record(node)

    async def search(
        self,
        search: TaskChoiceMemorySearch | None = None,
        *,
        mark_read: bool = True,
    ) -> list[TaskChoiceMemoryNode]:
        parts = build_memory_node_where(_memory_search_from_task_choice_memory_search(search))
        result = await self.database.query(
            f"""
            SELECT * FROM {TASK_CHOICE_MEMORIES_ROOT_ID}->contains->memory_node
            {parts.where_sql}
            ORDER BY updated_at DESC, created_at DESC;
            """,
            parts.variables,
        )
        records = _records(result)
        if mark_read:
            records = await self.database.mark_records_read(records)
        return [task_choice_memory_node_from_record(record) for record in records]


def _memory_search_from_task_choice_memory_search(
    search: TaskChoiceMemorySearch | None,
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


def task_choice_memory_node_from_record(
    record: Mapping[str, Any],
) -> TaskChoiceMemoryNode:
    return memory_node_from_record(record, _parse_task_choice_memory)


def _parse_task_choice_memory(content: Mapping[str, Any]) -> TaskChoiceMemory:
    return TaskChoiceMemory(
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
