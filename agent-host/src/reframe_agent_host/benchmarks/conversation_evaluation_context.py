from __future__ import annotations

from baml_sdk import context as baml_context
from baml_sdk import memory_search as baml_memory_search
from baml_sdk import task_routing as baml_task_routing
from reframe_agent_host.benchmarks.conversation_evaluation_case_types import (
    BenchmarkConversation,
    BenchmarkMemory,
    BenchmarkSelectedTask,
)


def conversation_context(
    conversations: tuple[BenchmarkConversation, ...],
) -> list[baml_context.ConversationHistory]:
    return [
        baml_context.ConversationHistory(
            id=conversation.id,
            name=conversation.name,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            read_at=conversation.read_at,
            messages=[
                baml_context.ConversationHistoryMessage(
                    created_at=message.created_at,
                    updated_at=message.updated_at,
                    read_at=message.read_at,
                    role=message.role,
                    content=message.content,
                )
                for message in conversation.messages
            ],
        )
        for conversation in conversations
    ]


def memory_context(memories: tuple[BenchmarkMemory, ...]) -> list[baml_context.SessionMemoryContext]:
    return [
        baml_context.SessionMemoryContext(
            title=memory.title,
            description=memory.description,
            tags=list(memory.tags),
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            read_at=memory.read_at,
        )
        for memory in memories
    ]


def conversation_evaluation_memory_context(
    memories: tuple[BenchmarkMemory, ...],
) -> list[baml_memory_search.ConversationEvaluationMemoryContext]:
    return [
        baml_memory_search.ConversationEvaluationMemoryContext(
            title=memory.title,
            description=memory.description,
            tags=list(memory.tags),
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            read_at=memory.read_at,
        )
        for memory in memories
    ]


def selected_task_context(task: BenchmarkSelectedTask) -> baml_task_routing.SelectedTaskContext:
    return baml_task_routing.SelectedTaskContext(
        id=task.id,
        name=task.name,
        description=task.description,
        input=task.input,
        output=task.output,
        prompt=task.prompt,
        provider_id=task.provider_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
        read_at=task.read_at,
    )
