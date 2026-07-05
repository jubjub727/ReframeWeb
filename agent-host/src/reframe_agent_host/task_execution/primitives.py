from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import Thread
from typing import Any

import baml_sdk as types
from reframe_agent_host.speech.tts import NoopSpeaker, TextSpeaker
from reframe_memory import (
    ConversationMessage,
    MemoryDatabase,
    SessionMemory,
    UserPreferenceMemory,
)


ACTION_NOT_SUPPORTED_REPLY = "Action not supported."

SUPPORTED_PRIMITIVES = {
    "agent_thought",
    "agent_reply",
    "conversation_mode_off",
    "session_memory",
    "user_preference",
}

UNSUPPORTED_PRIMITIVES = {
    "website_memory",
    "window_move",
    "window_resize",
    "window_minimize",
    "window_close",
    "window_open",
    "website_open",
    "website_read",
    "website_call",
}


@dataclass(frozen=True)
class PrimitiveDispatchRecord:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class PrimitiveDispatchResult:
    records: tuple[PrimitiveDispatchRecord, ...] = ()


@dataclass
class PrimitiveDispatcher:
    database: MemoryDatabase
    session_id: str | None = None
    conversation_id: str | None = None
    speaker: TextSpeaker | None = None
    on_event: Callable[[str, str], None] | None = None
    on_conversation_mode_off: Callable[[], None] | None = None

    async def dispatch(
        self,
        result: types.TaskExecutionResult | None,
    ) -> PrimitiveDispatchResult:
        if result is None:
            return PrimitiveDispatchResult()

        records = []
        for call in result.returns:
            records.append(await self._dispatch_call(call))
        return PrimitiveDispatchResult(records=tuple(records))

    async def _dispatch_call(
        self,
        call: types.TaskReturnItem,
    ) -> PrimitiveDispatchRecord:
        name = call.name.strip()
        if name in UNSUPPORTED_PRIMITIVES or name not in SUPPORTED_PRIMITIVES:
            await self._agent_reply(ACTION_NOT_SUPPORTED_REPLY)
            return PrimitiveDispatchRecord(
                name=name or "<empty>",
                status="unsupported",
                detail=ACTION_NOT_SUPPORTED_REPLY,
            )

        if name == "agent_reply":
            text = _payload_text(call.payload, "text", "message", "reply")
            if not text:
                await self._agent_reply(ACTION_NOT_SUPPORTED_REPLY)
                return _malformed(name)
            await self._agent_reply(text)
            return PrimitiveDispatchRecord(name=name, status="ok", detail=text)

        if name == "agent_thought":
            text = _payload_text(call.payload, "text", "thought", "message")
            if not text:
                await self._agent_reply(ACTION_NOT_SUPPORTED_REPLY)
                return _malformed(name)
            await self._agent_thought(text)
            return PrimitiveDispatchRecord(name=name, status="ok", detail=text)

        if name == "conversation_mode_off":
            if self.on_conversation_mode_off is not None:
                self.on_conversation_mode_off()
            self._emit("conversation-mode", "continuous conversation off")
            return PrimitiveDispatchRecord(
                name=name,
                status="ok",
                detail="continuous conversation off",
            )

        if name == "session_memory":
            if self.session_id is None:
                await self._agent_reply(ACTION_NOT_SUPPORTED_REPLY)
                return PrimitiveDispatchRecord(
                    name=name,
                    status="unsupported",
                    detail="missing session_id",
                )
            title, description = _memory_payload(call.payload, "Session memory")
            await self.database.session_memories.create(
                self.session_id,
                SessionMemory(title=title, description=description),
                tags=("task-execution", "session-memory"),
            )
            return PrimitiveDispatchRecord(name=name, status="ok", detail=title)

        if name == "user_preference":
            title, description = _memory_payload(call.payload, "User preference")
            await self.database.user_preferences.create(
                UserPreferenceMemory(title=title, description=description),
                tags=("task-execution", "user-preference"),
            )
            return PrimitiveDispatchRecord(name=name, status="ok", detail=title)

        await self._agent_reply(ACTION_NOT_SUPPORTED_REPLY)
        return PrimitiveDispatchRecord(
            name=name,
            status="unsupported",
            detail=ACTION_NOT_SUPPORTED_REPLY,
        )

    async def _agent_reply(self, text: str) -> None:
        if self.conversation_id is not None:
            await self.database.conversations.add_message(
                self.conversation_id,
                ConversationMessage(role="agent", content=text),
            )
        self._emit("agent-reply", text)
        self._speak_in_background(text)

    async def _agent_thought(self, text: str) -> None:
        if self.conversation_id is None:
            return
        await self.database.conversations.add_message(
            self.conversation_id,
            ConversationMessage(role="agent_thought", content=text),
        )
        self._emit("agent-thought", text)

    def _emit(self, stage: str, message: str) -> None:
        if self.on_event is not None:
            self.on_event(stage, message)

    def _speak_in_background(self, text: str) -> None:
        speaker = self.speaker or NoopSpeaker()

        def speak() -> None:
            try:
                speaker.speak(text)
            except Exception as exc:
                self._emit("tts-error", str(exc))

        Thread(target=speak, daemon=True).start()


def _payload_text(payload: Any, *keys: str) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, Mapping):
        for key in keys:
            value = payload.get(key)
            if value is not None:
                text = str(value).strip()
                if text:
                    return text
    return ""


def _memory_payload(payload: Any, default_title: str) -> tuple[str, str]:
    if isinstance(payload, Mapping):
        title = _first_text(payload, ("title", "name", "summary")) or default_title
        description = (
            _first_text(payload, ("description", "text", "memory", "value"))
            or title
        )
        return title, description

    text = str(payload).strip() if payload is not None else ""
    if not text:
        return default_title, default_title
    title = text[:80].strip()
    return title, text


def _first_text(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return ""


def _malformed(name: str) -> PrimitiveDispatchRecord:
    return PrimitiveDispatchRecord(
        name=name,
        status="malformed",
        detail=ACTION_NOT_SUPPORTED_REPLY,
    )
