from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from reframe_memory.ids import memory_node_record_id
from reframe_memory.filesystem_publication import publish_filesystem_memory
from reframe_memory.models import (
    CheckpointFilesystemMemory,
    DirectoryFilesystemMemory,
    FilesystemMemory,
    FilesystemMemoryNode,
)
from reframe_memory.query_results import records
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

    async def publish_directory(
        self,
        memory: DirectoryFilesystemMemory,
        tags: Sequence[str] = (),
    ) -> FilesystemMemoryNode:
        """Idempotently publish one canonical directory memory."""
        return await self._publish(
            filesystem_directory_memory_id(memory.source_path),
            memory,
            tags,
        )

    async def publish_checkpoint(
        self,
        memory: CheckpointFilesystemMemory,
        tags: Sequence[str] = (),
    ) -> FilesystemMemoryNode:
        """Idempotently publish a durable manifest as a graph memory root."""
        return await self._publish(
            filesystem_checkpoint_memory_id(memory.backing_store, memory.manifest_id),
            memory,
            tags,
        )

    async def _publish(
        self,
        memory_id: str,
        memory: FilesystemMemory,
        tags: Sequence[str],
    ) -> FilesystemMemoryNode:
        record_id = memory_node_record_id(memory_id)
        await publish_filesystem_memory(
            self.database,
            root_id=FILESYSTEM_MEMORIES_ROOT_ID,
            record_id=record_id,
            memory=memory,
            tags=_normalized_tags(tags),
            identity=_persistent_identity(memory),
        )
        published = await self._get_record(record_id)
        if published is None:
            raise ValueError(f"filesystem memory publication disappeared: {record_id}")
        if _persistent_identity(published.content) != _persistent_identity(memory):
            raise ValueError(f"filesystem memory id collision: {record_id}")
        return published

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

    async def _get_record(self, record_id: str) -> FilesystemMemoryNode | None:
        result = await self.database.query(f"SELECT * FROM {record_id} LIMIT 1;")
        found = records(result)
        return filesystem_memory_from_record(found[0]) if found else None


def filesystem_memory_from_record(record: Mapping[str, Any]) -> FilesystemMemoryNode:
    return memory_node_from_record(record, _parse_memory)


def _parse_memory(content: Mapping[str, Any]) -> FilesystemMemory:
    source_kind = str(content.get("source_kind") or "directory")
    common = {
        "title": str(content["title"]),
        "description": str(content["description"]),
        "base_memory_ids": tuple(
            str(value) for value in content.get("base_memory_ids") or ()
        ),
    }
    if source_kind == "directory":
        source_path = _optional_string(content.get("source_path"))
        if source_path is None:
            raise ValueError("directory filesystem memory is missing source_path")
        return DirectoryFilesystemMemory(source_path=source_path, **common)
    if source_kind == "checkpoint":
        backing_store = _optional_string(content.get("backing_store"))
        manifest_id = _optional_string(content.get("manifest_id"))
        if backing_store is None or manifest_id is None:
            raise ValueError("checkpoint filesystem memory is missing its locator")
        return CheckpointFilesystemMemory(
            backing_store=backing_store,
            manifest_id=manifest_id,
            **common,
        )
    raise ValueError(f"unsupported filesystem memory source: {source_kind}")


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _persistent_identity(memory: FilesystemMemory) -> tuple[object, ...]:
    if isinstance(memory, DirectoryFilesystemMemory):
        return (memory.source_kind, _canonical_path(memory.source_path))
    if isinstance(memory, CheckpointFilesystemMemory):
        return (
            memory.source_kind,
            _canonical_path(memory.backing_store),
            memory.manifest_id,
            memory.base_memory_ids,
        )
    raise TypeError(f"unsupported filesystem memory type: {type(memory).__name__}")


def filesystem_directory_memory_id(source_path: str) -> str:
    return _scoped_memory_id("directory", _canonical_path(source_path))


def filesystem_checkpoint_memory_id(backing_store: str, manifest_id: str) -> str:
    return _scoped_memory_id("checkpoint", _canonical_path(backing_store), manifest_id)


def _scoped_memory_id(kind: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join((kind, *parts)).encode("utf-8")).hexdigest()
    return f"memory_node:filesystem_{kind}_{digest}"


def _canonical_path(value: str) -> str:
    return os.path.normcase(str(Path(value).expanduser().resolve()))


def _normalized_tags(tags: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
