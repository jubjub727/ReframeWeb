from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkConversationMessage:
    created_at: str
    updated_at: str
    read_at: str
    role: str
    content: str


@dataclass(frozen=True)
class BenchmarkConversation:
    id: str
    name: str
    created_at: str
    updated_at: str
    read_at: str
    messages: tuple[BenchmarkConversationMessage, ...]


@dataclass(frozen=True)
class BenchmarkMemory:
    title: str
    description: str
    tags: tuple[str, ...]
    created_at: str
    updated_at: str
    read_at: str


@dataclass(frozen=True)
class BenchmarkSelectedTask:
    id: str
    name: str
    description: str
    input: str
    output: str
    prompt: str
    provider_id: str
    created_at: str
    updated_at: str
    read_at: str


@dataclass(frozen=True)
class ConversationEvaluationBenchmarkCase:
    id: str
    current_user_request: str
    selected_task: BenchmarkSelectedTask
    session_conversations: tuple[BenchmarkConversation, ...] = ()
    session_memories: tuple[BenchmarkMemory, ...] = ()
    conversation_evaluation_memories: tuple[BenchmarkMemory, ...] = ()
    review_focus: str = ""
