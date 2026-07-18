from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from reframe_memory.ids import memory_node_record_id
from reframe_memory.models import FilesystemMemory, FilesystemMemoryNode
from reframe_memory.query_results import first_record, records
from reframe_memory.records import memory_node_from_record

if TYPE_CHECKING:
    from reframe_memory.database import MemoryDatabase


FILESYSTEM_MEMORIES_ROOT_ID = "memory_root:filesystem_memories"


@dataclass
class FilesystemMemoryStore:
    database: MemoryDatabase

    async def ensure_root(self) -> None:
        await self.database.query(
            f"""
            UPSERT {FILESYSTEM_MEMORIES_ROOT_ID} SET
                name = 'Filesystem Memories',
                description = 'Directories available for projection into agent workspaces';
            """,
        )

    async def create(
        self,
        memory: FilesystemMemory,
        tags: Sequence[str] = (),
    ) -> FilesystemMemoryNode:
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
        record = first_record(result)
        await self.database.query(
            f"RELATE {FILESYSTEM_MEMORIES_ROOT_ID}->contains->$node_id;",
            {"node_id": record["id"]},
        )
        return filesystem_memory_from_record(record)

    async def publish_checkpoint(
        self,
        memory_id: str,
        memory: FilesystemMemory,
        tags: Sequence[str] = (),
    ) -> FilesystemMemoryNode:
        """Idempotently publish a durable manifest as a graph memory root."""
        record_id = memory_node_record_id(memory_id)
        existing = await self.get(record_id, mark_read=False)
        if existing is not None:
            if _persistent_identity(existing.content) != _persistent_identity(memory):
                raise ValueError(f"filesystem memory id collision: {record_id}")
            return existing
        result = await self.database.query(
            f"""
            CREATE {record_id} SET
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
        record = first_record(result)
        await self.database.query(
            f"RELATE {FILESYSTEM_MEMORIES_ROOT_ID}->contains->{record_id};",
        )
        return filesystem_memory_from_record(record)

    async def get(
        self,
        memory_id: str,
        *,
        mark_read: bool = True,
    ) -> FilesystemMemoryNode | None:
        record_id = memory_node_record_id(memory_id)
        result = await self.database.query(
            f"""
            SELECT * FROM {FILESYSTEM_MEMORIES_ROOT_ID}->contains->memory_node
            WHERE id = {record_id}
            LIMIT 1;
            """,
        )
        found = records(result)
        if not found:
            return None
        if mark_read:
            found = await self.database.mark_records_read(found)
        return filesystem_memory_from_record(found[0])

    async def list(self, *, mark_read: bool = False) -> list[FilesystemMemoryNode]:
        result = await self.database.query(
            f"""
            SELECT * FROM {FILESYSTEM_MEMORIES_ROOT_ID}->contains->memory_node
            ORDER BY updated_at DESC, created_at DESC;
            """,
        )
        found = records(result)
        if mark_read:
            found = await self.database.mark_records_read(found)
        return [filesystem_memory_from_record(record) for record in found]


def filesystem_memory_from_record(record: Mapping[str, Any]) -> FilesystemMemoryNode:
    return memory_node_from_record(record, _parse_memory)


def _parse_memory(content: Mapping[str, Any]) -> FilesystemMemory:
    source_kind = str(content.get("source_kind") or "directory")
    return FilesystemMemory(
        title=str(content["title"]),
        description=str(content["description"]),
        source_kind=source_kind,  # type: ignore[arg-type]
        source_path=_optional_string(content.get("source_path")),
        backing_store=_optional_string(content.get("backing_store")),
        manifest_id=_optional_string(content.get("manifest_id")),
        base_memory_ids=tuple(str(value) for value in content.get("base_memory_ids") or ()),
    )


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _persistent_identity(memory: FilesystemMemory) -> tuple[object, ...]:
    return (
        memory.source_kind,
        memory.source_path,
        memory.backing_store,
        memory.manifest_id,
        memory.base_memory_ids,
    )
