from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from reframe_agent_host.agent_flow.timestamps import timestamp_fields
from reframe_agent_host.agent_flow.machine_state import local_machine_state_context
import baml_sdk as baml
import baml_sdk as types
from reframe_agent_host.agent_flow.baml_clients import client_kwargs
from reframe_agent_host.agent_flow.session_context import (
    current_conversation_history,
    session_memory_contexts,
)
from reframe_memory import MemoryDatabase, TaskNode, open_memory_database


def current_timestamp() -> str:
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return stamp.replace("+00:00", "Z")


def default_search_domains() -> list[types.SearchDepthDomain]:
    return [
        types.SearchDepthDomain(
            id="task_catalog",
            description=(
                "Historic task catalog records. Use this domain when older task "
                "definitions may help interpret or run the selected task."
            ),
            searches="Task memory nodes only.",
            hydrates="Matched Task nodes only.",
        ),
        types.SearchDepthDomain(
            id="past_conversation_context",
            description=(
                "Historic conversation context outside the current default "
                "session context. Use this domain when earlier sessions, "
                "conversations, messages, or session memories may clarify the "
                "request."
            ),
            searches=(
                "Session nodes, Conversation nodes, ConversationMessage nodes, "
                "and SessionMemory nodes attached to those past sessions."
            ),
            hydrates=(
                "The containing Session node, relevant Conversation nodes, "
                "matched ConversationMessage nodes, and relevant SessionMemory "
                "nodes from that session."
            ),
        ),
    ]


@dataclass(frozen=True)
class SearchDepthContext:
    current_conversation: types.ConversationHistory | None
    session_memories: list[types.SessionMemoryContext]
    selected_task: types.SelectedTaskContext
    search_depth_memories: list[types.SearchDepthMemoryContext]
    search_domains: list[types.SearchDepthDomain]


@dataclass
class SearchDepthContextBuilder:
    database: MemoryDatabase
    selected_task_id: str
    session_id: str | None = None
    conversation_id: str | None = None

    async def build(self) -> SearchDepthContext:
        return SearchDepthContext(
            current_conversation=await self._current_conversation(),
            session_memories=await self._session_memories(),
            selected_task=await self._selected_task(),
            search_depth_memories=await self._search_depth_memories(),
            search_domains=default_search_domains(),
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

    async def _search_depth_memories(self) -> list[types.SearchDepthMemoryContext]:
        memories = await self.database.search_depth_memories.search()
        return [
            types.SearchDepthMemoryContext(
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                **timestamp_fields(memory),
            )
            for memory in memories
        ]


class SearchDepthPlanner:
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

    async def evaluate_search_depths(
        self,
        current_user_request: str,
        selected_task_id: str,
        memory_search_hints: types.ConversationMemorySearchHints,
    ) -> types.SearchDepthDecision:
        database = await self._get_database()
        context = await SearchDepthContextBuilder(
            database=database,
            session_id=self._session_id,
            conversation_id=self._conversation_id,
            selected_task_id=selected_task_id,
        ).build()

        return await baml.ChooseMemorySearchDepths_async(
            current_timestamp=current_timestamp(),
            current_user_request=current_user_request,
            current_conversation=context.current_conversation,
            session_memories=context.session_memories,
            selected_task=context.selected_task,
            memory_search_hints=memory_search_hints,
            search_domains=context.search_domains,
            search_depth_memories=context.search_depth_memories,
            machine_state=local_machine_state_context(
                "No voice startup machine state provider"
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
