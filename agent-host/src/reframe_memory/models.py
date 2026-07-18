from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    model_id: str | None = None
    reasoning_effort: str | None = None


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
    role: Literal[
        "human",
        "agent",
        "agent_thought",
        "agent_reply_interrupted",
        "validation_reply",
    ]
    content: str


@dataclass(frozen=True)
class SessionMemory:
    title: str
    description: str


@dataclass(frozen=True, kw_only=True)
class FilesystemMemory(ABC):
    title: str
    description: str
    base_memory_ids: tuple[str, ...] = ()

    @property
    @abstractmethod
    def source_kind(self) -> Literal["directory", "checkpoint"]:
        """Discriminator supplied by concrete, persistable memory variants."""


@dataclass(frozen=True, kw_only=True)
class DirectoryFilesystemMemory(FilesystemMemory):
    source_path: str
    source_kind: Literal["directory"] = field(default="directory", init=False)

    def __post_init__(self) -> None:
        if not self.source_path:
            raise ValueError("directory filesystem memory source_path cannot be empty")


@dataclass(frozen=True, kw_only=True)
class CheckpointFilesystemMemory(FilesystemMemory):
    backing_store: str
    manifest_id: str
    source_kind: Literal["checkpoint"] = field(default="checkpoint", init=False)

    def __post_init__(self) -> None:
        if not self.backing_store or not self.manifest_id:
            raise ValueError(
                "checkpoint filesystem memories require backing_store and manifest_id"
            )


@dataclass(frozen=True)
class ContextMemory:
    title: str
    description: str


@dataclass(frozen=True)
class TaskHistory:
    pass


@dataclass(frozen=True)
class TaskHistoryNode:
    session: str
    conversation: str


@dataclass(frozen=True)
class SessionAction:
    pass


@dataclass(frozen=True)
class Action:
    name: str
    input: object
    output: object


ProviderNode: TypeAlias = MemoryNode[Provider]
TaskNode: TypeAlias = MemoryNode[Task]
SessionNode: TypeAlias = MemoryNode[Session]
ConversationNode: TypeAlias = MemoryNode[Conversation]
ConversationMessageNode: TypeAlias = MemoryNode[ConversationMessage]
SessionMemoryNode: TypeAlias = MemoryNode[SessionMemory]
FilesystemMemoryNode: TypeAlias = MemoryNode[FilesystemMemory]
UserPreferenceMemory: TypeAlias = ContextMemory
TaskChoiceMemory: TypeAlias = ContextMemory
ConversationEvaluationMemory: TypeAlias = ContextMemory
SearchDepthMemory: TypeAlias = ContextMemory
RelevanceMemory: TypeAlias = ContextMemory
TaskPromptMemory: TypeAlias = ContextMemory
UserPreferenceMemoryNode: TypeAlias = MemoryNode[ContextMemory]
TaskChoiceMemoryNode: TypeAlias = MemoryNode[ContextMemory]
ConversationEvaluationMemoryNode: TypeAlias = MemoryNode[ContextMemory]
SearchDepthMemoryNode: TypeAlias = MemoryNode[ContextMemory]
RelevanceMemoryNode: TypeAlias = MemoryNode[ContextMemory]
TaskPromptMemoryNode: TypeAlias = MemoryNode[ContextMemory]
TaskHistoryMemoryNode: TypeAlias = MemoryNode[TaskHistory]
TaskHistoryNodeMemoryNode: TypeAlias = MemoryNode[TaskHistoryNode]
SessionActionNode: TypeAlias = MemoryNode[SessionAction]
ActionNode: TypeAlias = MemoryNode[Action]
