from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock

from baml_sdk import turn_context as baml_turn_context
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
        self._active_human_replies: set[str] = set()
        self._last_captured_at: datetime | None = None

    def add_message(
        self,
        conversation_id: str | None,
        *,
        role: str,
        content: str,
    ) -> str | None:
        if conversation_id is None:
            return None
        clean = " ".join(content.split())
        if not clean:
            return None
        with self._lock:
            captured_at = self._next_captured_at()
            message = LiveConversationMessage(
                conversation_id=memory_node_record_id(conversation_id),
                role=role,
                content=clean,
                captured_at=captured_at,
            )
            self._messages.append(message)
            if role == "human":
                self._active_human_replies.add(message.captured_at)
        return message.captured_at

    def _next_captured_at(self) -> str:
        captured_at = datetime.now(UTC)
        if (
            self._last_captured_at is not None
            and captured_at <= self._last_captured_at
        ):
            captured_at = self._last_captured_at + timedelta(microseconds=1)
        self._last_captured_at = captured_at
        return captured_at.isoformat().replace("+00:00", "Z")

    def resolve_human_reply(self, captured_at: str | None) -> None:
        if captured_at is None:
            return
        with self._lock:
            self._active_human_replies.discard(captured_at)

    def active_human_reply_created_at(
        self,
        conversation_id: str | None,
    ) -> list[str]:
        if conversation_id is None:
            return []
        expected_conversation_id = memory_node_record_id(conversation_id)
        with self._lock:
            return [
                message.captured_at
                for message in self._messages
                if message.conversation_id == expected_conversation_id
                and message.captured_at in self._active_human_replies
            ]

    def merge(
        self,
        conversation: baml_turn_context.ConversationHistory | None,
        conversation_id: str | None,
    ) -> baml_turn_context.ConversationHistory | None:
        if conversation_id is None:
            return conversation

        expected_conversation_id = memory_node_record_id(conversation_id)
        live_messages = self._messages_for(expected_conversation_id)
        if not live_messages:
            return conversation

        if conversation is None:
            now = _timestamp()
            return baml_turn_context.ConversationHistory(
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
        active_human_replies = set(
            self.active_human_reply_created_at(conversation_id)
        )
        for message in live_messages:
            if message.captured_at not in active_human_replies:
                continue
            _replace_persisted_active_reply(merged, message)
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

        return baml_turn_context.ConversationHistory(
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
) -> baml_turn_context.ConversationHistoryMessage:
    return baml_turn_context.ConversationHistoryMessage(
        created_at=message.captured_at,
        updated_at=message.captured_at,
        read_at="NONE",
        role=message.role,
        content=message.content,
    )


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _replace_persisted_active_reply(merged, live_message) -> None:
    live_created_at = _parse_timestamp(live_message.captured_at)
    for index in range(len(merged) - 1, -1, -1):
        message = merged[index]
        if (
            message.role != live_message.role
            or message.content != live_message.content
        ):
            continue
        if message.created_at == live_message.captured_at:
            return
        persisted_created_at = _parse_timestamp(message.created_at)
        if persisted_created_at is not None and (
            live_created_at is None or persisted_created_at >= live_created_at
        ):
            merged.pop(index)
            return


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
