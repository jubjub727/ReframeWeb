from __future__ import annotations

from dataclasses import dataclass

from reframe_agent_host.agent_flow.relevance_candidates import candidate_contexts
from reframe_agent_host.agent_flow.session_context import (
    current_conversation_history,
    session_memory_contexts,
)
from reframe_agent_host.agent_flow.timestamps import timestamp_fields
import baml_sdk as baml
import baml_sdk as types
from reframe_agent_host.agent_flow.baml_clients import client_kwargs
from reframe_memory import MemoryDatabase, TaskNode, open_memory_database
from reframe_memory.retrieved_context import RetrievedMemoryContext


@dataclass(frozen=True)
class MemoryRelevanceContext:
    current_conversation: types.ConversationHistory | None
    session_memories: list[types.SessionMemoryContext]
    selected_task: types.SelectedTaskContext
    candidate_memories: list[types.RetrievedMemoryCandidate]
    relevance_memories: list[types.RelevanceMemoryContext]


@dataclass
class MemoryRelevanceContextBuilder:
    database: MemoryDatabase
    selected_task_id: str
    retrieved_memories: RetrievedMemoryContext
    session_id: str | None = None
    conversation_id: str | None = None

    async def build(self) -> MemoryRelevanceContext:
        return MemoryRelevanceContext(
            current_conversation=await self._current_conversation(),
            session_memories=await self._session_memories(),
            selected_task=await self._selected_task(),
            candidate_memories=candidate_contexts(
                self.retrieved_memories,
                current_session_id=self.session_id,
            ),
            relevance_memories=await self._relevance_memories(),
        )

    async def _current_conversation(self) -> types.ConversationHistory | None:
        return await current_conversation_history(
            self.database,
            self.session_id,
            self.conversation_id,
        )

    async def _session_memories(self) -> list[types.SessionMemoryContext]:
        return await session_memory_contexts(self.database, self.session_id)

    async def _selected_task(self) -> types.SelectedTaskContext:
        task = await self.database.tasks.get(self.selected_task_id)
        if task is None:
            msg = f"selected task does not exist: {self.selected_task_id}"
            raise ValueError(msg)

        return _selected_task_context(task)

    async def _relevance_memories(self) -> list[types.RelevanceMemoryContext]:
        memories = await self.database.relevance_memories.search()
        return [
            types.RelevanceMemoryContext(
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                **timestamp_fields(memory),
            )
            for memory in memories
        ]


class MemoryRelevancePlanner:
    def __init__(
        self,
        database: MemoryDatabase | None = None,
        session_id: str | None = None,
        conversation_id: str | None = None,
        client_name: str | None = None,
    ) -> None:
        self._database = database
        self._owns_database = database is None
        self._session_id = session_id
        self._conversation_id = conversation_id
        self._client_name = client_name

    async def evaluate_relevant_memories(
        self,
        current_user_request: str,
        selected_task_id: str,
        retrieved_memories: RetrievedMemoryContext,
    ) -> types.RelevantMemoryDecision:
        database = await self._get_database()
        context = await MemoryRelevanceContextBuilder(
            database=database,
            session_id=self._session_id,
            conversation_id=self._conversation_id,
            selected_task_id=selected_task_id,
            retrieved_memories=retrieved_memories,
        ).build()

        return await baml.EvaluateRelevantMemories_async(
            current_user_request=current_user_request,
            current_conversation=context.current_conversation,
            session_memories=context.session_memories,
            selected_task=context.selected_task,
            candidate_memories=context.candidate_memories,
            relevance_memories=context.relevance_memories,
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
