from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeAlias, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class MemoryTimestamps:
    """
    Global timestamps for every memory node.

    created_at is when the memory was first stored. updated_at is when its
    stored content or model-facing metadata last changed. read_at is when an
    agent intentionally loaded the memory for use; None means it has not been
    read before.
    """

    created_at: datetime
    updated_at: datetime
    read_at: datetime | None


@dataclass(frozen=True)
class MemoryNode(Generic[T]):
    id: str
    tags: tuple[str, ...]
    timestamps: MemoryTimestamps
    content: T


@dataclass(frozen=True)
class Task:
    name: str
    description: str
    input: str
    output: str
    prompt: str


TaskNode: TypeAlias = MemoryNode[Task]
