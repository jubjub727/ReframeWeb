from __future__ import annotations

from collections.abc import Iterable

from reframe_agent_host.agent_flow.timestamps import timestamp_fields
import baml_sdk as types
from reframe_memory.retrieved_context import (
    RetrievedConversation,
    RetrievedMemoryContext,
    RetrievedPastConversationContext,
    RetrievedSessionContext,
    RetrievedTaskCatalog,
)


def candidate_contexts(
    memories: RetrievedMemoryContext,
    current_session_id: str | None = None,
) -> list[types.RetrievedMemoryCandidate]:
    candidates: list[types.RetrievedMemoryCandidate] = []
    candidates.extend(_task_candidates(memories))
    candidates.extend(_current_session_memory_candidates(memories, current_session_id))
    candidates.extend(_past_conversation_candidates(memories, current_session_id))
    return candidates


def filter_retrieved_memories(
    memories: RetrievedMemoryContext,
    decision: types.RelevantMemoryDecision,
) -> RetrievedMemoryContext:
    kept_ids = set(decision.kept_memory_ids)
    return RetrievedMemoryContext(
        task_catalog=RetrievedTaskCatalog(
            tasks=tuple(
                task for task in memories.task_catalog.tasks if task.id in kept_ids
            )
        ),
        past_conversation_context=RetrievedPastConversationContext(
            sessions=tuple(
                session
                for session in (
                    _filter_session_context(session, kept_ids)
                    for session in memories.past_conversation_context.sessions
                )
                if session is not None
            )
        ),
        current_session_memories=tuple(
            memory
            for memory in memories.current_session_memories
            if memory.id in kept_ids
        ),
    )


def _task_candidates(
    memories: RetrievedMemoryContext,
) -> Iterable[types.RetrievedMemoryCandidate]:
    for task in memories.task_catalog.tasks:
        yield types.RetrievedMemoryCandidate(
            id=task.id,
            kind="task",
            title=task.content.name,
            description=_task_description(task),
            tags=list(task.tags),
            retrieval_matched=True,
            parent_session_id=None,
            parent_conversation_id=None,
            **timestamp_fields(task),
        )


def _current_session_memory_candidates(
    memories: RetrievedMemoryContext,
    current_session_id: str | None,
) -> Iterable[types.RetrievedMemoryCandidate]:
    for memory in memories.current_session_memories:
        yield types.RetrievedMemoryCandidate(
            id=memory.id,
            kind="current_session_memory",
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            retrieval_matched=False,
            parent_session_id=current_session_id,
            parent_conversation_id=None,
            **timestamp_fields(memory),
        )


def _past_conversation_candidates(
    memories: RetrievedMemoryContext,
    current_session_id: str | None,
) -> Iterable[types.RetrievedMemoryCandidate]:
    for session in memories.past_conversation_context.sessions:
        is_current_session = _is_current_session(session, current_session_id)
        yield _session_candidate(session, is_current_session)
        for memory in session.session_memories:
            yield types.RetrievedMemoryCandidate(
                id=memory.id,
                kind=(
                    "current_session_memory"
                    if is_current_session
                    else "past_session_memory"
                ),
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                retrieval_matched=True,
                parent_session_id=session.session.id,
                parent_conversation_id=None,
                **timestamp_fields(memory),
            )
        for conversation in session.conversations:
            yield _conversation_candidate(session, conversation, is_current_session)
            matched_message_ids = _matched_message_ids(conversation)
            for message in conversation.messages:
                yield types.RetrievedMemoryCandidate(
                    id=message.id,
                    kind=(
                        "current_conversation_message"
                        if is_current_session
                        else "past_conversation_message"
                    ),
                    title=f"{message.content.role} message",
                    description=message.content.content,
                    tags=list(message.tags),
                    retrieval_matched=message.id in matched_message_ids,
                    parent_session_id=session.session.id,
                    parent_conversation_id=conversation.conversation.id,
                    **timestamp_fields(message),
                )


def _session_candidate(
    session: RetrievedSessionContext,
    is_current_session: bool,
) -> types.RetrievedMemoryCandidate:
    return types.RetrievedMemoryCandidate(
        id=session.session.id,
        kind="current_session" if is_current_session else "past_session",
        title=session.session.content.name,
        description=(
            "Current session wrapper."
            if is_current_session
            else "Past session wrapper."
        ),
        tags=list(session.session.tags),
        retrieval_matched=session.matched,
        parent_session_id=None,
        parent_conversation_id=None,
        **timestamp_fields(session.session),
    )


def _conversation_candidate(
    session: RetrievedSessionContext,
    conversation: RetrievedConversation,
    is_current_session: bool,
) -> types.RetrievedMemoryCandidate:
    return types.RetrievedMemoryCandidate(
        id=conversation.conversation.id,
        kind="current_conversation" if is_current_session else "past_conversation",
        title=conversation.conversation.content.name,
        description=(
            "Current conversation wrapper."
            if is_current_session
            else "Past conversation wrapper."
        ),
        tags=list(conversation.conversation.tags),
        retrieval_matched=conversation.matched,
        parent_session_id=session.session.id,
        parent_conversation_id=None,
        **timestamp_fields(conversation.conversation),
    )


def _is_current_session(
    session: RetrievedSessionContext,
    current_session_id: str | None,
) -> bool:
    return current_session_id is not None and session.session.id == current_session_id


def _matched_message_ids(conversation: RetrievedConversation) -> set[str]:
    matched_ids = getattr(conversation, "matched_message_ids", ())
    if matched_ids:
        return set(matched_ids)
    return {message.id for message in conversation.messages}


def _filter_session_context(
    session: RetrievedSessionContext,
    kept_ids: set[str],
) -> RetrievedSessionContext | None:
    conversations = tuple(
        conversation
        for conversation in (
            _filter_conversation(conversation, kept_ids)
            for conversation in session.conversations
        )
        if conversation is not None
    )
    session_memories = tuple(
        memory for memory in session.session_memories if memory.id in kept_ids
    )
    if session.session.id not in kept_ids and not conversations and not session_memories:
        return None

    return RetrievedSessionContext(
        session=session.session,
        matched=session.matched,
        conversations=conversations,
        session_memories=session_memories,
    )


def _filter_conversation(
    conversation: RetrievedConversation,
    kept_ids: set[str],
) -> RetrievedConversation | None:
    messages = tuple(
        message for message in conversation.messages if message.id in kept_ids
    )
    if conversation.conversation.id not in kept_ids and not messages:
        return None

    return RetrievedConversation(
        conversation=conversation.conversation,
        matched=conversation.matched,
        messages=messages,
        matched_message_ids=tuple(
            message_id
            for message_id in getattr(conversation, "matched_message_ids", ())
            if message_id in kept_ids
        ),
    )


def _task_description(task) -> str:
    pieces = [
        ("description", task.content.description),
        ("input", task.content.input),
        ("output", task.content.output),
        ("prompt", task.content.prompt),
        ("provider_id", task.content.provider_id),
    ]
    return "\n".join(f"{label}: {value}" for label, value in pieces if value)
