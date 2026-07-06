from __future__ import annotations

import baml_sdk as types
from reframe_agent_host.agent_flow.timestamps import timestamp_fields
from reframe_memory import MemoryDatabase


async def session_conversation_history(
    database: MemoryDatabase,
    session_id: str | None,
) -> list[types.ConversationHistory]:
    if session_id is None:
        return []

    conversations = await database.sessions.conversations_for(session_id)
    history = []
    for conversation in conversations:
        messages = await database.conversations.messages_for(conversation.id)
        history.append(
            types.ConversationHistory(
                id=conversation.id,
                name=conversation.content.name,
                **timestamp_fields(conversation),
                messages=[
                    types.ConversationHistoryMessage(
                        **timestamp_fields(message),
                        role=message.content.role,
                        content=message.content.content,
                    )
                    for message in messages
                ],
            )
        )
    return history


async def session_memory_contexts(
    database: MemoryDatabase,
    session_id: str | None,
) -> list[types.SessionMemoryContext]:
    if session_id is None:
        return []

    memories = await database.session_memories.for_session(session_id)
    return [
        types.SessionMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in memories
    ]
