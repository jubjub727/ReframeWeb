from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from reframe_memory.models import Task, TaskNode
from reframe_memory.records import memory_node_from_record
from reframe_memory.search import MemoryNodeSearch, TagSearch, build_memory_node_where

if TYPE_CHECKING:
    from reframe_memory.database import MemoryDatabase


TASKS_ROOT_ID = "memory_root:tasks"
TASKS_ROOT_NAME = "Tasks"
TASKS_ROOT_DESCRIPTION = (
    "Nodes connected from this root are Task control-flow primitives. "
    "Each node content object is a Task with name, description, input, output, and prompt."
)


@dataclass(frozen=True)
class TaskSearch:
    tags: TagSearch = TagSearch()
    names: tuple[str, ...] = ()
    descriptions: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    prompts: tuple[str, ...] = ()

    @classmethod
    def build(
        cls,
        *,
        tags: TagSearch | None = None,
        names: Sequence[str] = (),
        descriptions: Sequence[str] = (),
        inputs: Sequence[str] = (),
        outputs: Sequence[str] = (),
        prompts: Sequence[str] = (),
    ) -> "TaskSearch":
        return cls(
            tags=tags or TagSearch(),
            names=tuple(names),
            descriptions=tuple(descriptions),
            inputs=tuple(inputs),
            outputs=tuple(outputs),
            prompts=tuple(prompts),
        )


@dataclass
class TaskMemory:
    database: MemoryDatabase

    async def ensure_root(self) -> None:
        await self.database.query(
            f"""
            UPSERT {TASKS_ROOT_ID} SET
                name = $name,
                description = $description;
            """,
            {
                "name": TASKS_ROOT_NAME,
                "description": TASKS_ROOT_DESCRIPTION,
            },
        )

    async def create(self, task: Task, tags: Sequence[str] = ()) -> TaskNode:
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
                "content": asdict(task),
            },
        )
        node = _first_record(result)
        await self.database.query(
            f"RELATE {TASKS_ROOT_ID}->contains->$node_id;",
            {"node_id": node["id"]},
        )
        return _parse_task_node(node)

    async def search(self, search: TaskSearch | None = None) -> list[TaskNode]:
        parts = build_memory_node_where(_memory_search_from_task_search(search))
        result = await self.database.query(
            f"""
            SELECT * FROM {TASKS_ROOT_ID}->contains->memory_node
            {parts.where_sql}
            ORDER BY updated_at DESC, created_at DESC;
            """,
            parts.variables,
        )
        return [_parse_task_node(record) for record in _records(result)]


def _memory_search_from_task_search(search: TaskSearch | None) -> MemoryNodeSearch | None:
    if search is None:
        return None

    return MemoryNodeSearch(
        tags=search.tags,
        content_contains={
            "name": search.names,
            "description": search.descriptions,
            "input": search.inputs,
            "output": search.outputs,
            "prompt": search.prompts,
        },
    )


def _parse_task_node(record: Mapping[str, Any]) -> TaskNode:
    return memory_node_from_record(record, _parse_task)


def _parse_task(content: Mapping[str, Any]) -> Task:
    return Task(
        name=str(content["name"]),
        description=str(content["description"]),
        input=str(content["input"]),
        output=str(content["output"]),
        prompt=str(content["prompt"]),
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
