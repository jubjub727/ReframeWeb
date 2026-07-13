from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from inspect import Parameter, signature
from threading import Thread
from typing import Any

from baml_sdk import task as baml_task
from reframe_agent_host.speech.tts import NoopSpeaker, TextSpeaker
from reframe_agent_host.task_execution.primitive_payloads import (
    action_not_supported_detail,
    malformed_detail,
    memory_payload,
    payload_text,
)
from reframe_memory import (
    ConversationMessage,
    MemoryDatabase,
    SessionMemory,
    UserPreferenceMemory,
    open_memory_database,
)


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
    output: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PrimitiveDispatchResult:
    records: tuple[PrimitiveDispatchRecord, ...] = ()
    task_history_id: str | None = None
    task_history_node_id: str | None = None


@dataclass
class PrimitiveDispatcher:
    database: MemoryDatabase
    session_id: str | None = None
    conversation_id: str | None = None
    task_history_id: str | None = None
    speaker: TextSpeaker | None = None
    on_event: Callable[[str, str], None] | None = None
    on_conversation_mode_off: Callable[[], None] | None = None

    async def dispatch(
        self,
        result: baml_task.TaskExecutionResult | None,
    ) -> PrimitiveDispatchResult:
        if result is None:
            return PrimitiveDispatchResult()

        records = []
        session_action_ids: list[str] = []
        task_history_id = await self._ensure_task_history()
        for call in result.returns:
            record = await self._dispatch_call(call)
            records.append(record)
            session_action_id = await self._record_action(call, record)
            if session_action_id is not None:
                session_action_ids.append(session_action_id)
        task_history_node_id = await self._append_task_history_node(
            task_history_id,
            session_action_ids,
        )
        return PrimitiveDispatchResult(
            records=tuple(records),
            task_history_id=task_history_id,
            task_history_node_id=task_history_node_id,
        )

    async def _dispatch_call(
        self,
        call: baml_task.TaskReturnItem,
    ) -> PrimitiveDispatchRecord:
        name = call.name.strip()
        if name in UNSUPPORTED_PRIMITIVES or name not in SUPPORTED_PRIMITIVES:
            detail = action_not_supported_detail(name, call.payload)
            message_id = await self._agent_reply(detail)
            return PrimitiveDispatchRecord(
                name=name or "<empty>",
                status="unsupported",
                detail=detail,
                output={
                    "status": "unsupported",
                    "detail": detail,
                    "message": message_id,
                },
            )

        if name == "agent_reply":
            text = payload_text(call.payload, "text", "message", "reply")
            if not text:
                detail = malformed_detail(name, call.payload)
                message_id = await self._agent_reply(detail)
                return _malformed(name, detail, message_id=message_id)
            message_id = await self._agent_reply(text)
            return PrimitiveDispatchRecord(
                name=name,
                status="ok",
                detail=text,
                output={
                    "status": "ok",
                    "message": message_id,
                    "text": text,
                },
            )

        if name == "agent_thought":
            text = payload_text(call.payload, "text", "thought", "message")
            if not text:
                detail = malformed_detail(name, call.payload)
                message_id = await self._agent_reply(detail)
                return _malformed(name, detail, message_id=message_id)
            message_id = await self._agent_thought(text)
            return PrimitiveDispatchRecord(
                name=name,
                status="ok",
                detail=text,
                output={
                    "status": "ok",
                    "message": message_id,
                    "text": text,
                },
            )

        if name == "conversation_mode_off":
            if self.on_conversation_mode_off is not None:
                self.on_conversation_mode_off()
            self._emit("conversation-mode", "continuous conversation off")
            return PrimitiveDispatchRecord(
                name=name,
                status="ok",
                detail="continuous conversation off",
                output={
                    "status": "ok",
                    "conversation_mode": "off",
                },
            )

        if name == "session_memory":
            if self.session_id is None:
                detail = action_not_supported_detail(
                    name,
                    call.payload,
                    reason="missing session_id",
                )
                message_id = await self._agent_reply(detail)
                return PrimitiveDispatchRecord(
                    name=name,
                    status="unsupported",
                    detail=detail,
                    output={
                        "status": "unsupported",
                        "detail": detail,
                        "message": message_id,
                    },
                )
            title, description = memory_payload(call.payload, "Session memory")
            memory = await self.database.session_memories.create(
                self.session_id,
                SessionMemory(title=title, description=description),
                tags=("task-execution", "session-memory"),
            )
            return PrimitiveDispatchRecord(
                name=name,
                status="ok",
                detail=title,
                output={
                    "status": "ok",
                    "memory": memory.id,
                    "title": title,
                    "description": description,
                },
            )

        if name == "user_preference":
            title, description = memory_payload(call.payload, "User preference")
            memory = await self.database.user_preferences.create(
                UserPreferenceMemory(title=title, description=description),
                tags=("task-execution", "user-preference"),
            )
            return PrimitiveDispatchRecord(
                name=name,
                status="ok",
                detail=title,
                output={
                    "status": "ok",
                    "memory": memory.id,
                    "title": title,
                    "description": description,
                },
            )

        detail = action_not_supported_detail(name, call.payload)
        message_id = await self._agent_reply(detail)
        return PrimitiveDispatchRecord(
            name=name,
            status="unsupported",
            detail=detail,
            output={
                "status": "unsupported",
                "detail": detail,
                "message": message_id,
            },
        )

    async def _agent_reply(self, text: str) -> str | None:
        message_id = None
        if self.conversation_id is not None:
            message = await self.database.conversations.add_message(
                self.conversation_id,
                ConversationMessage(role="agent", content=text),
            )
            message_id = getattr(message, "id", None)
        self._emit("agent-reply", text)
        self._speak_in_background(text)
        return message_id

    async def _agent_thought(self, text: str) -> str | None:
        if self.conversation_id is None:
            return None
        message = await self.database.conversations.add_message(
            self.conversation_id,
            ConversationMessage(role="agent_thought", content=text),
        )
        self._emit("agent-thought", text)
        return getattr(message, "id", None)

    async def _ensure_task_history(self) -> str | None:
        if self.session_id is None or self.conversation_id is None:
            return None
        if self.task_history_id is not None:
            return self.task_history_id
        task_history = await self.database.task_history.create(
            tags=("task-execution",),
        )
        self.task_history_id = task_history.id
        return task_history.id

    async def _record_action(
        self,
        call: baml_task.TaskReturnItem,
        record: PrimitiveDispatchRecord,
    ) -> str | None:
        if self.task_history_id is None:
            return None
        session_action = await self.database.task_history.record_action(
            name=record.name,
            input=call.payload or {},
            output=dict(record.output),
            tags=("task-execution",),
        )
        return session_action.id

    async def _append_task_history_node(
        self,
        task_history_id: str | None,
        session_action_ids: list[str],
    ) -> str | None:
        if (
            task_history_id is None
            or self.session_id is None
            or self.conversation_id is None
        ):
            return None
        node = await self.database.task_history.append_node(
            task_history_id,
            session_id=self.session_id,
            conversation_id=self.conversation_id,
            actions=session_action_ids,
            tags=("task-execution",),
        )
        return node.id

    def _emit(self, stage: str, message: str) -> None:
        if self.on_event is not None:
            self.on_event(stage, message)

    def _speak_in_background(self, text: str) -> None:
        speaker = self.speaker or NoopSpeaker()

        def on_speech_event(stage: str, message: str) -> None:
            if stage == "tts-interrupted":
                detail = _single_line(message)
                self._emit("agent-reply-interrupted", detail)
                self._record_agent_reply_interrupted_in_background(detail)
            self._emit(stage, message)

        def speak() -> None:
            try:
                _speak_with_events(speaker, text, on_speech_event)
            except Exception as exc:
                self._emit("tts-error", str(exc))

        Thread(target=speak, daemon=True).start()

    def _record_agent_reply_interrupted_in_background(self, detail: str) -> None:
        if self.conversation_id is None:
            return

        def record() -> None:
            try:
                asyncio.run(self._record_agent_reply_interrupted(detail))
            except Exception as exc:
                self._emit(
                    "warning",
                    f"failed to record interrupted agent reply: {exc}",
                )

        Thread(target=record, daemon=True).start()

    async def _record_agent_reply_interrupted(self, detail: str) -> None:
        if self.conversation_id is None:
            return
        database = await open_memory_database()
        try:
            await database.conversations.add_message(
                self.conversation_id,
                ConversationMessage(
                    role="agent_reply_interrupted",
                    content=detail,
                ),
            )
        finally:
            await database.close()


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _malformed(
    name: str,
    detail: str,
    *,
    message_id: str | None,
) -> PrimitiveDispatchRecord:
    return PrimitiveDispatchRecord(
        name=name,
        status="malformed",
        detail=detail,
        output={
            "status": "malformed",
            "detail": detail,
            "message": message_id,
        },
    )


def _speak_with_events(
    speaker: TextSpeaker,
    text: str,
    on_event: Callable[[str, str], None],
) -> None:
    if _accepts_on_event(speaker.speak):
        speaker.speak(text, on_event=on_event)
        return
    speaker.speak(text)


def _accepts_on_event(callable_object: Callable[..., object]) -> bool:
    try:
        parameters = signature(callable_object).parameters
    except (TypeError, ValueError):
        return False
    return "on_event" in parameters or any(
        parameter.kind == Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
