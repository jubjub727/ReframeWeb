from __future__ import annotations

from dataclasses import dataclass

import baml_sdk as baml
import baml_sdk as types
from reframe_agent_host.agent_flow.baml_clients import client_kwargs
from reframe_agent_host.agent_flow.timestamps import timestamp_fields
from reframe_memory import MemoryDatabase, TaskNode, open_memory_database


@dataclass(frozen=True)
class ConversationEvaluationContext:
    session_conversations: list[types.ConversationHistory]
    session_memories: list[types.SessionMemoryContext]
    selected_task: types.SelectedTaskContext
    conversation_evaluation_memories: list[types.ConversationEvaluationMemoryContext]


@dataclass
class ConversationEvaluationContextBuilder:
    database: MemoryDatabase
    selected_task_id: str
    session_id: str | None = None

    async def build(self) -> ConversationEvaluationContext:
        return ConversationEvaluationContext(
            session_conversations=await self._session_conversations(),
            session_memories=await self._session_memories(),
            selected_task=await self._selected_task(),
            conversation_evaluation_memories=(
                await self._conversation_evaluation_memories()
            ),
        )

    async def _session_conversations(self) -> list[types.ConversationHistory]:
        if self.session_id is None:
            return []

        conversations = await self.database.sessions.conversations_for(self.session_id)
        history = []
        for conversation in conversations:
            messages = await self.database.conversations.messages_for(conversation.id)
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

    async def _session_memories(self) -> list[types.SessionMemoryContext]:
        if self.session_id is None:
            return []

        memories = await self.database.session_memories.for_session(self.session_id)
        return [
            types.SessionMemoryContext(
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                **timestamp_fields(memory),
            )
            for memory in memories
        ]

    async def _selected_task(self) -> types.SelectedTaskContext:
        task = await self.database.tasks.get(self.selected_task_id)
        if task is None:
            msg = f"selected task does not exist: {self.selected_task_id}"
            raise ValueError(msg)

        return _selected_task_context(task)

    async def _conversation_evaluation_memories(
        self,
    ) -> list[types.ConversationEvaluationMemoryContext]:
        memories = await self.database.conversation_evaluation_memories.search()
        return [
            types.ConversationEvaluationMemoryContext(
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                **timestamp_fields(memory),
            )
            for memory in memories
        ]


class ConversationEvaluationPlanner:
    def __init__(
        self,
        database: MemoryDatabase | None = None,
        session_id: str | None = None,
        client_name: str | None = None,
    ) -> None:
        self._database = database
        self._owns_database = database is None
        self._session_id = session_id
        self._client_name = client_name

    async def evaluate_for_memory_search(
        self,
        current_user_request: str,
        selected_task_id: str,
    ) -> types.ConversationMemorySearchHints:
        database = await self._get_database()
        context = await ConversationEvaluationContextBuilder(
            database=database,
            session_id=self._session_id,
            selected_task_id=selected_task_id,
        ).build()

        return await baml.EvaluateConversationForMemorySearch_async(
            current_user_request=current_user_request,
            session_conversations=context.session_conversations,
            session_memories=context.session_memories,
            selected_task=context.selected_task,
            conversation_evaluation_memories=(
                context.conversation_evaluation_memories
            ),
            **client_kwargs(self._client_name),
        )

    async def close(self) -> None:
        if self._database is not None and self._owns_database:
            await self._database.close()
            self._database = None

    async def _get_database(self) -> MemoryDatabase:
        if self._database is None:
            self._database = await open_memory_database()
            await self._database.apply_schema()
            await self._database.ensure_roots()
        return self._database


def _selected_task_context(task: TaskNode) -> types.SelectedTaskContext:
    return types.SelectedTaskContext(
        id=task.id,
        name=task.content.name,
        description=task.content.description,
        input=task.content.input,
        output=task.content.output,
        prompt=task.content.prompt,
        provider_id=task.content.provider_id,
        **timestamp_fields(task),
    )
