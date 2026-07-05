from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from reframe_memory.ids import memory_node_record_id
from reframe_memory.models import (
    ConversationMessageNode,
    SessionMemoryNode,
    SessionNode,
)
from reframe_memory.retrieval_terms import (
    GraphSearchHints,
    TimestampBreadth,
    candidate_matches,
)
from reframe_memory.retrieved_context import (
    RetrievedConversation,
    RetrievedMemoryContext,
    RetrievedPastConversationContext,
    RetrievedSessionContext,
    RetrievedTaskCatalog,
)

if TYPE_CHECKING:
    from reframe_memory.database import MemoryDatabase


TASK_CATALOG_DOMAIN = "task_catalog"
PAST_CONVERSATION_CONTEXT_DOMAIN = "past_conversation_context"


@dataclass(frozen=True)
class GraphRetrievalRequest:
    hints: GraphSearchHints
    depths: Mapping[str, TimestampBreadth]


@dataclass
class GraphMemoryRetriever:
    database: "MemoryDatabase"
    current_session_id: str | None = None

    async def retrieve(self, request: GraphRetrievalRequest) -> RetrievedMemoryContext:
        return RetrievedMemoryContext(
            task_catalog=await self._task_catalog(request),
            past_conversation_context=await self._past_conversation_context(request),
            current_session_memories=await self._current_session_memories(),
        )

    async def _current_session_memories(self) -> tuple[SessionMemoryNode, ...]:
        current_session_id = _normalized_session_id(self.current_session_id)
        if current_session_id is None:
            return ()
        return tuple(await self.database.sessions.memories_for(current_session_id))

    async def _task_catalog(
        self,
        request: GraphRetrievalRequest,
    ) -> RetrievedTaskCatalog:
        breadth = request.depths.get(TASK_CATALOG_DOMAIN)
        if breadth is None:
            return RetrievedTaskCatalog()

        tasks = await _without_mark_read(self.database.tasks.search)
        matched = tuple(
            task
            for task in tasks
            if candidate_matches(
                task,
                fields=(
                    "name",
                    "description",
                    "input",
                    "output",
                    "prompt",
                    "provider_id",
                ),
                hints=request.hints,
                breadth=breadth,
            )
        )
        await self._mark_record_ids_read([task.id for task in matched])
        return RetrievedTaskCatalog(tasks=matched)

    async def _past_conversation_context(
        self,
        request: GraphRetrievalRequest,
    ) -> RetrievedPastConversationContext:
        breadth = request.depths.get(PAST_CONVERSATION_CONTEXT_DOMAIN)
        if breadth is None:
            return RetrievedPastConversationContext()

        sessions = await _without_mark_read(self.database.sessions.search)
        current_session_id = _normalized_session_id(self.current_session_id)
        retrieved_sessions = []
        for session in sessions:
            if session.id == current_session_id:
                continue

            context = await self._session_context(
                session,
                request.hints,
                breadth,
            )
            if context is not None:
                retrieved_sessions.append(context)

        return RetrievedPastConversationContext(sessions=tuple(retrieved_sessions))

    async def _session_context(
        self,
        session: SessionNode,
        hints: GraphSearchHints,
        breadth: TimestampBreadth,
    ) -> RetrievedSessionContext | None:
        session_matched = candidate_matches(
            session,
            fields=("name",),
            hints=hints,
            breadth=breadth,
        )
        conversations = await self._conversation_contexts(session.id, hints, breadth)
        session_memories = await self._session_memory_candidates(
            session.id,
            hints,
            breadth,
        )
        if not session_matched and not conversations and not session_memories:
            return None

        await self._mark_record_ids_read([session.id])
        return RetrievedSessionContext(
            session=session,
            matched=session_matched,
            conversations=conversations,
            session_memories=session_memories,
        )

    async def _conversation_contexts(
        self,
        session_id: str,
        hints: GraphSearchHints,
        breadth: TimestampBreadth,
    ) -> tuple[RetrievedConversation, ...]:
        conversations = await _without_mark_read(
            self.database.sessions.conversations_for,
            session_id,
        )
        matched_contexts = []
        for conversation in conversations:
            conversation_matched = candidate_matches(
                conversation,
                fields=("name",),
                hints=hints,
                breadth=breadth,
            )
            messages = await self._message_candidates(
                conversation.id,
                hints,
                breadth,
            )
            if conversation_matched or messages:
                await self._mark_record_ids_read([conversation.id])
                matched_contexts.append(
                    RetrievedConversation(
                        conversation=conversation,
                        matched=conversation_matched,
                        messages=messages,
                    )
                )
        return tuple(matched_contexts)

    async def _message_candidates(
        self,
        conversation_id: str,
        hints: GraphSearchHints,
        breadth: TimestampBreadth,
    ) -> tuple[ConversationMessageNode, ...]:
        messages = await _without_mark_read(
            self.database.conversations.messages_for,
            conversation_id,
        )
        matched = tuple(
            message
            for message in messages
            if candidate_matches(
                message,
                fields=("role", "content"),
                hints=hints,
                breadth=breadth,
            )
        )
        await self._mark_record_ids_read([message.id for message in matched])
        return matched

    async def _session_memory_candidates(
        self,
        session_id: str,
        hints: GraphSearchHints,
        breadth: TimestampBreadth,
    ) -> tuple[SessionMemoryNode, ...]:
        memories = await _without_mark_read(
            self.database.sessions.memories_for,
            session_id,
        )
        matched = tuple(
            memory
            for memory in memories
            if candidate_matches(
                memory,
                fields=("title", "description"),
                hints=hints,
                breadth=breadth,
            )
        )
        await self._mark_record_ids_read([memory.id for memory in matched])
        return matched

    async def _mark_record_ids_read(self, record_ids: list[str]) -> None:
        mark = getattr(self.database, "mark_record_ids_read", None)
        if mark is not None:
            await mark(record_ids)


def _normalized_session_id(session_id: str | None) -> str | None:
    if session_id is None:
        return None
    return memory_node_record_id(session_id)


async def _without_mark_read(method, *args):
    try:
        return await method(*args, mark_read=False)
    except TypeError as exc:
        if "mark_read" not in str(exc):
            raise
        return await method(*args)
