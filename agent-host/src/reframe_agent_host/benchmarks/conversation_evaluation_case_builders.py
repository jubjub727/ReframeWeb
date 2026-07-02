from __future__ import annotations

from reframe_agent_host.benchmarks.conversation_evaluation_case_types import (
    BenchmarkConversation,
    BenchmarkConversationMessage,
    BenchmarkMemory,
)


def conversation(
    id_suffix: str,
    name: str,
    messages: tuple[BenchmarkConversationMessage, ...],
) -> BenchmarkConversation:
    return BenchmarkConversation(
        id=f"benchmark_conversation:{id_suffix}",
        name=name,
        created_at=messages[0].created_at,
        updated_at=messages[-1].updated_at,
        read_at="NONE",
        messages=messages,
    )


def human(content: str, created_at: str) -> BenchmarkConversationMessage:
    return message("human", content, created_at)


def agent(content: str, created_at: str) -> BenchmarkConversationMessage:
    return message("agent", content, created_at)


def thought(content: str, created_at: str) -> BenchmarkConversationMessage:
    return message("agent_thought", content, created_at)


def message(
    role: str,
    content: str,
    created_at: str,
) -> BenchmarkConversationMessage:
    return BenchmarkConversationMessage(
        created_at=created_at,
        updated_at=created_at,
        read_at="NONE",
        role=role,
        content=content,
    )


def memory(
    title: str,
    description: str,
    tags: tuple[str, ...],
    created_at: str,
) -> BenchmarkMemory:
    return BenchmarkMemory(
        title=title,
        description=description,
        tags=tags,
        created_at=created_at,
        updated_at=created_at,
        read_at="NONE",
    )
