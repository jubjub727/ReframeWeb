from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock

import baml_sdk as types
from reframe_memory.ids import memory_node_record_id


@dataclass(frozen=True)
class LiveConversationMessage:
    conversation_id: str
    role: str
    content: str
    captured_at: str


class LiveConversationContext:
    def __init__(self) -> None:
        self._lock = Lock()
        self._messages: list[LiveConversationMessage] = []

    def add_message(
        self,
        conversation_id: str | None,
        *,
        role: str,
        content: str,
    ) -> None:
        if conversation_id is None:
            return
        clean = " ".join(content.split())
        if not clean:
            return
        message = LiveConversationMessage(
            conversation_id=memory_node_record_id(conversation_id),
            role=role,
            content=clean,
            captured_at=_timestamp(),
        )
        with self._lock:
            self._messages.append(message)

    def merge(
        self,
        conversation: types.ConversationHistory | None,
        conversation_id: str | None,
    ) -> types.ConversationHistory | None:
        if conversation_id is None:
            return conversation

        expected_conversation_id = memory_node_record_id(conversation_id)
        live_messages = self._messages_for(expected_conversation_id)
        if not live_messages:
            return conversation

        if conversation is None:
            now = _timestamp()
            return types.ConversationHistory(
                id=expected_conversation_id,
                name="Current conversation",
                created_at=now,
                updated_at=now,
                read_at="NONE",
                messages=[
                    _history_message(message)
                    for message in live_messages
                ],
            )

        merged = list(conversation.messages)
        persisted_counts = Counter(
            (message.role, message.content)
            for message in merged
        )
        for message in live_messages:
            key = (message.role, message.content)
            if persisted_counts[key] > 0:
                persisted_counts[key] -= 1
                continue
            merged.append(_history_message(message))

        return types.ConversationHistory(
            id=conversation.id,
            name=conversation.name,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            read_at=conversation.read_at,
            messages=merged,
        )

    def _messages_for(self, conversation_id: str) -> list[LiveConversationMessage]:
        with self._lock:
            return [
                message
                for message in self._messages
                if message.conversation_id == conversation_id
            ]


def _history_message(
    message: LiveConversationMessage,
) -> types.ConversationHistoryMessage:
    return types.ConversationHistoryMessage(
        created_at=message.captured_at,
        updated_at=message.captured_at,
        read_at="NONE",
        role=message.role,
        content=message.content,
    )


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
