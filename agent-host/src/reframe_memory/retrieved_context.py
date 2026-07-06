from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from reframe_memory.models import (
    ConversationMessageNode,
    ConversationNode,
    MemoryNode,
    SessionMemoryNode,
    SessionNode,
    TaskNode,
)


@dataclass(frozen=True)
class RetrievedTaskCatalog:
    tasks: tuple[TaskNode, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"tasks": [_node_to_dict(task) for task in self.tasks]}


@dataclass(frozen=True)
class RetrievedConversation:
    conversation: ConversationNode
    matched: bool
    messages: tuple[ConversationMessageNode, ...] = ()
    matched_message_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "conversation": _node_to_dict(self.conversation),
            "matched": self.matched,
            "messages": [_node_to_dict(message) for message in self.messages],
            "matched_message_ids": list(self.matched_message_ids),
        }


@dataclass(frozen=True)
class RetrievedSessionContext:
    session: SessionNode
    matched: bool
    conversations: tuple[RetrievedConversation, ...] = ()
    session_memories: tuple[SessionMemoryNode, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "session": _node_to_dict(self.session),
            "matched": self.matched,
            "conversations": [
                conversation.to_dict() for conversation in self.conversations
            ],
            "session_memories": [
                _node_to_dict(memory) for memory in self.session_memories
            ],
        }


@dataclass(frozen=True)
class RetrievedPastConversationContext:
    sessions: tuple[RetrievedSessionContext, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "sessions": [session.to_dict() for session in self.sessions],
        }


@dataclass(frozen=True)
class RetrievedMemoryContext:
    task_catalog: RetrievedTaskCatalog = field(default_factory=RetrievedTaskCatalog)
    past_conversation_context: RetrievedPastConversationContext = (
        field(default_factory=RetrievedPastConversationContext)
    )
    current_session_memories: tuple[SessionMemoryNode, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "task_catalog": self.task_catalog.to_dict(),
            "past_conversation_context": self.past_conversation_context.to_dict(),
            "current_session_memories": [
                _node_to_dict(memory) for memory in self.current_session_memories
            ],
        }


def _node_to_dict(node: MemoryNode[Any]) -> dict[str, object]:
    timestamps = node.timestamps
    return {
        "id": node.id,
        "tags": list(node.tags),
        "created_at": timestamps.created_at.isoformat(),
        "updated_at": timestamps.updated_at.isoformat(),
        "read_at": timestamps.read_at.isoformat() if timestamps.read_at else "NONE",
        "content": asdict(node.content),
    }
