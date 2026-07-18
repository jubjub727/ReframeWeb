from __future__ import annotations

from dataclasses import asdict
import json
from typing import TYPE_CHECKING

from reframe_memory.models import (
    CheckpointFilesystemMemory,
    DirectoryFilesystemMemory,
    FilesystemMemory,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from reframe_memory.database import MemoryDatabase


async def publish_filesystem_memory(
    database: MemoryDatabase,
    *,
    root_id: str,
    record_id: str,
    memory: FilesystemMemory,
    tags: Sequence[str],
    identity: tuple[object, ...],
) -> None:
    """Atomically validate, upsert, and link a canonical filesystem memory."""
    await database.query(
        _publication_query(root_id, record_id),
        {
            "tags": list(tags),
            "content": asdict(memory),
            "identity": json.dumps(identity, separators=(",", ":")),
            "source_kind": getattr(memory, "source_kind", None),
            "source_path": (
                memory.source_path
                if isinstance(memory, DirectoryFilesystemMemory)
                else None
            ),
            "backing_store": (
                memory.backing_store
                if isinstance(memory, CheckpointFilesystemMemory)
                else None
            ),
            "manifest_id": (
                memory.manifest_id
                if isinstance(memory, CheckpointFilesystemMemory)
                else None
            ),
            "base_memory_ids": list(memory.base_memory_ids),
        },
    )


def _publication_query(root_id: str, record_id: str) -> str:
    return f"""
        BEGIN TRANSACTION;
        LET $existing = SELECT * FROM ONLY {record_id};
        LET $legacy_identity_matches = IF $existing = NONE {{
            true
        }} ELSE IF $existing.content.source_kind = 'directory' {{
            $source_kind = 'directory'
                AND $existing.content.source_path = $source_path
        }} ELSE IF $existing.content.source_kind = 'checkpoint' {{
            $source_kind = 'checkpoint'
                AND $existing.content.backing_store = $backing_store
                AND $existing.content.manifest_id = $manifest_id
                AND $existing.content.base_memory_ids = $base_memory_ids
        }} ELSE {{
            false
        }};
        LET $identity_conflicts = $existing != NONE
            AND $existing.filesystem_identity != $identity
            AND NOT (
                $existing.filesystem_identity = NONE
                AND $legacy_identity_matches
            );
        IF !$identity_conflicts {{
            LET $now = time::now();
            UPSERT {record_id} SET
                tags = $tags,
                content = $content,
                filesystem_identity = $identity,
                created_at = IF $existing = NONE {{ $now }} ELSE {{ $existing.created_at }},
                updated_at = IF $existing = NONE
                    OR $existing.tags != $tags
                    OR $existing.content != $content
                    {{ $now }} ELSE {{ $existing.updated_at }},
                read_at = IF $existing = NONE {{ NONE }} ELSE {{ $existing.read_at }};
            DELETE contains WHERE in = {root_id} AND out = {record_id};
            RELATE {root_id}->contains->{record_id};
        }};
        COMMIT TRANSACTION;
    """
