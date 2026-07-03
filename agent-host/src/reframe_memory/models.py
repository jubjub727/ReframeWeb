from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Literal, TypeAlias, TypeVar


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
class Provider:
    name: str
    description: str
    baml_surface: str


@dataclass(frozen=True)
class Task:
    name: str
    description: str
    input: str
    output: str
    prompt: str
    provider_id: str


@dataclass(frozen=True)
class Session:
    name: str


@dataclass(frozen=True)
class Conversation:
    name: str


@dataclass(frozen=True)
class ConversationMessage:
    role: Literal["human", "agent", "agent_thought"]
    content: str


@dataclass(frozen=True)
class SessionMemory:
    title: str
    description: str


@dataclass(frozen=True)
class TaskChoiceMemory:
    title: str
    description: str


@dataclass(frozen=True)
class ConversationEvaluationMemory:
    title: str
    description: str


@dataclass(frozen=True)
class SearchDepthMemory:
    title: str
    description: str


ProviderNode: TypeAlias = MemoryNode[Provider]
TaskNode: TypeAlias = MemoryNode[Task]
SessionNode: TypeAlias = MemoryNode[Session]
ConversationNode: TypeAlias = MemoryNode[Conversation]
ConversationMessageNode: TypeAlias = MemoryNode[ConversationMessage]
SessionMemoryNode: TypeAlias = MemoryNode[SessionMemory]
TaskChoiceMemoryNode: TypeAlias = MemoryNode[TaskChoiceMemory]
ConversationEvaluationMemoryNode: TypeAlias = MemoryNode[ConversationEvaluationMemory]
SearchDepthMemoryNode: TypeAlias = MemoryNode[SearchDepthMemory]
