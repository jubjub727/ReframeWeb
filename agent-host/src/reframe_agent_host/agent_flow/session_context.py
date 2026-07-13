from __future__ import annotations

from baml_sdk import turn_context as baml_turn_context
from reframe_agent_host.agent_flow.timestamps import timestamp_fields
from reframe_memory import ConversationNode, MemoryDatabase
from reframe_memory.ids import memory_node_record_id


async def current_conversation_history(
    database: MemoryDatabase,
    session_id: str | None,
    conversation_id: str | None,
) -> baml_turn_context.ConversationHistory | None:
    if session_id is None or conversation_id is None:
        return None

    expected_conversation_id = memory_node_record_id(conversation_id)
    conversations = await database.sessions.conversations_for(session_id)
    for conversation in conversations:
        if conversation.id == expected_conversation_id:
            return await conversation_history(database, conversation)
    return None


async def conversation_history(
    database: MemoryDatabase,
    conversation: ConversationNode,
) -> baml_turn_context.ConversationHistory:
    messages = await database.conversations.messages_for(conversation.id)
    return baml_turn_context.ConversationHistory(
        id=conversation.id,
        name=conversation.content.name,
        **timestamp_fields(conversation),
        messages=[
            baml_turn_context.ConversationHistoryMessage(
                **timestamp_fields(message),
                role=message.content.role,
                content=message.content.content,
            )
            for message in messages
        ],
    )


async def session_memory_contexts(
    database: MemoryDatabase,
    session_id: str | None,
) -> list[baml_turn_context.SessionMemoryContext]:
    if session_id is None:
        return []

    memories = await database.session_memories.for_session(session_id)
    return [
        baml_turn_context.SessionMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in memories
    ]
