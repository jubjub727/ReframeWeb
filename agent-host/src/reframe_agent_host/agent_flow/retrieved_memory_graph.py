from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from baml_sdk import retrieved_memory as baml_retrieved_memory
from reframe_agent_host.agent_flow.timestamps import timestamp_fields
from reframe_memory.retrieved_context import RetrievedMemoryContext


def retrieved_memory_graph(memories: RetrievedMemoryContext) -> baml_retrieved_memory.RetrievedMemoryGraph:
    return baml_retrieved_memory.RetrievedMemoryGraph(
        task_catalog=[
            baml_retrieved_memory.RetrievedTaskNode(
                id=task.id,
                name=task.content.name,
                description=task.content.description,
                input=task.content.input,
                output=task.content.output,
                prompt=task.content.prompt,
                provider_id=task.content.provider_id,
                tags=list(task.tags),
                **timestamp_fields(task),
            )
            for task in memories.task_catalog.tasks
        ],
        past_sessions=[
            baml_retrieved_memory.RetrievedSessionGraph(
                session=baml_retrieved_memory.RetrievedSessionNode(
                    id=session.session.id,
                    name=session.session.content.name,
                    tags=list(session.session.tags),
                    **timestamp_fields(session.session),
                ),
                matched=session.matched,
                conversations=[
                    baml_retrieved_memory.RetrievedConversationGraph(
                        conversation=baml_retrieved_memory.RetrievedConversationNode(
                            id=conversation.conversation.id,
                            name=conversation.conversation.content.name,
                            tags=list(conversation.conversation.tags),
                            **timestamp_fields(conversation.conversation),
                        ),
                        matched=conversation.matched,
                        messages=[
                            baml_retrieved_memory.RetrievedConversationMessageNode(
                                id=message.id,
                                role=message.content.role,
                                content=message.content.content,
                                tags=list(message.tags),
                                **timestamp_fields(message),
                            )
                            for message in conversation.messages
                        ],
                        matched_message_ids=list(
                            getattr(conversation, "matched_message_ids", ())
                        ),
                    )
                    for conversation in session.conversations
                ],
                session_memories=[
                    baml_retrieved_memory.RetrievedSessionMemoryNode(
                        id=memory.id,
                        title=memory.content.title,
                        description=memory.content.description,
                        tags=list(memory.tags),
                        **timestamp_fields(memory),
                    )
                    for memory in session.session_memories
                ],
            )
            for session in memories.past_conversation_context.sessions
        ],
        current_session_memories=[
            baml_retrieved_memory.RetrievedSessionMemoryNode(
                id=memory.id,
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                **timestamp_fields(memory),
            )
            for memory in memories.current_session_memories
        ],
    )


@dataclass(frozen=True)
class BamlRetrievedMemoryContext:
    task_catalog: Any
    past_conversation_context: Any
    current_session_memories: tuple[Any, ...]

    @classmethod
    def from_graph(cls, graph: baml_retrieved_memory.RetrievedMemoryGraph) -> "BamlRetrievedMemoryContext":
        return cls(
            task_catalog=SimpleNamespace(tasks=tuple(graph.task_catalog)),
            past_conversation_context=SimpleNamespace(
                sessions=tuple(
                    SimpleNamespace(
                        session=session.session,
                        matched=session.matched,
                        conversations=tuple(
                            SimpleNamespace(
                                conversation=conversation.conversation,
                                matched=conversation.matched,
                                messages=tuple(conversation.messages),
                                matched_message_ids=tuple(
                                    conversation.matched_message_ids
                                ),
                            )
                            for conversation in session.conversations
                        ),
                        session_memories=tuple(session.session_memories),
                    )
                    for session in graph.past_sessions
                )
            ),
            current_session_memories=tuple(graph.current_session_memories),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "task_catalog": {
                "tasks": [_task_to_dict(task) for task in self.task_catalog.tasks],
            },
            "past_conversation_context": {
                "sessions": [
                    {
                        "session": _session_to_dict(session.session),
                        "matched": session.matched,
                        "conversations": [
                            {
                                "conversation": _conversation_to_dict(
                                    conversation.conversation
                                ),
                                "matched": conversation.matched,
                                "messages": [
                                    _message_to_dict(message)
                                    for message in conversation.messages
                                ],
                                "matched_message_ids": list(
                                    conversation.matched_message_ids
                                ),
                            }
                            for conversation in session.conversations
                        ],
                        "session_memories": [
                            _session_memory_to_dict(memory)
                            for memory in session.session_memories
                        ],
                    }
                    for session in self.past_conversation_context.sessions
                ],
            },
            "current_session_memories": [
                _session_memory_to_dict(memory)
                for memory in self.current_session_memories
            ],
        }


def _timestamps(node: Any) -> dict[str, str]:
    return {
        "created_at": node.created_at,
        "updated_at": node.updated_at,
        "read_at": node.read_at,
    }


def _base_node(node: Any, content: dict[str, object]) -> dict[str, object]:
    return {
        "id": node.id,
        "tags": list(node.tags),
        **_timestamps(node),
        "content": content,
    }


def _task_to_dict(task: Any) -> dict[str, object]:
    return _base_node(
        task,
        {
            "name": task.name,
            "description": task.description,
            "input": task.input,
            "output": task.output,
            "prompt": task.prompt,
            "provider_id": task.provider_id,
        },
    )


def _session_to_dict(session: Any) -> dict[str, object]:
    return _base_node(session, {"name": session.name})


def _conversation_to_dict(conversation: Any) -> dict[str, object]:
    return _base_node(conversation, {"name": conversation.name})


def _message_to_dict(message: Any) -> dict[str, object]:
    return _base_node(
        message,
        {
            "role": message.role,
            "content": message.content,
        },
    )


def _session_memory_to_dict(memory: Any) -> dict[str, object]:
    return _base_node(
        memory,
        {
            "title": memory.title,
            "description": memory.description,
        },
    )
