from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from reframe_memory.models import MemoryNode, MemoryTimestamps


T = TypeVar("T")


def memory_node_from_record(
    record: Mapping[str, Any],
    parse_content: Callable[[Mapping[str, Any]], T],
) -> MemoryNode[T]:
    content = record.get("content")
    if not isinstance(content, Mapping):
        msg = f"memory node {record.get('id')} has no object content"
        raise ValueError(msg)

    return MemoryNode(
        id=str(record["id"]),
        tags=tuple(record.get("tags") or ()),
        timestamps=MemoryTimestamps(
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            read_at=record.get("read_at"),
        ),
        content=parse_content(content),
    )
