from __future__ import annotations

from dataclasses import dataclass

from baml_sdk import context as baml_context
from baml_sdk import task_routing as baml_task_routing
from reframe_agent_host.agent_flow.provider_clients import client_kwargs
from reframe_agent_host.agent_flow.machine_state import local_machine_state_context
from reframe_agent_host.agent_flow.session_context import (
    current_conversation_history,
    session_memory_contexts,
)
from reframe_agent_host.agent_flow.timestamps import timestamp_fields
from reframe_memory import MemoryDatabase, open_memory_database


@dataclass(frozen=True)
class TaskChoiceContext:
    current_conversation: baml_context.ConversationHistory | None
    session_memories: list[baml_context.SessionMemoryContext]
    user_preferences: list[baml_context.UserPreferenceMemoryContext]
    available_tasks: list[baml_task_routing.AvailableTask]
    task_choice_memories: list[baml_task_routing.TaskChoiceMemoryContext]


@dataclass
class TaskChoiceContextBuilder:
    database: MemoryDatabase
    session_id: str | None = None
    conversation_id: str | None = None

    async def build(self) -> TaskChoiceContext:
        return TaskChoiceContext(
            current_conversation=await self._current_conversation(),
            session_memories=await self._session_memories(),
            user_preferences=await self._user_preferences(),
            available_tasks=await self._available_tasks(),
            task_choice_memories=await self._task_choice_memories(),
        )

    async def _current_conversation(
        self,
    ) -> baml_context.ConversationHistory | None:
        return await current_conversation_history(
            self.database,
            self.session_id,
            self.conversation_id,
        )

    async def _session_memories(self) -> list[baml_context.SessionMemoryContext]:
        return await session_memory_contexts(self.database, self.session_id)

    async def _user_preferences(self) -> list[baml_context.UserPreferenceMemoryContext]:
        memories = await self.database.user_preferences.search()
        return [
            baml_context.UserPreferenceMemoryContext(
                id=memory.id,
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                **timestamp_fields(memory),
            )
            for memory in memories
        ]

    async def _available_tasks(self) -> list[baml_task_routing.AvailableTask]:
        tasks = await self.database.tasks.search()
        return [
            baml_task_routing.AvailableTask(
                id=task.id,
                name=task.content.name,
                description=task.content.description,
                input=task.content.input,
                output=task.content.output,
                prompt=task.content.prompt,
                provider_id=task.content.provider_id,
                **timestamp_fields(task),
            )
            for task in tasks
        ]

    async def _task_choice_memories(self) -> list[baml_task_routing.TaskChoiceMemoryContext]:
        memories = await self.database.task_choice_memories.search()
        return [
            baml_task_routing.TaskChoiceMemoryContext(
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                **timestamp_fields(memory),
            )
            for memory in memories
        ]


class TaskChoicePlanner:
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

    async def choose_initial_task(
        self,
        current_user_request: str,
    ) -> baml_task_routing.TaskChoiceDecision:
        database = await self._get_database()
        context = await TaskChoiceContextBuilder(
            database=database,
            session_id=self._session_id,
            conversation_id=self._conversation_id,
        ).build()

        return await baml_task_routing.ChooseTask_async(
            current_user_request=current_user_request,
            current_conversation=context.current_conversation,
            session_memories=context.session_memories,
            user_preferences=context.user_preferences,
            available_tasks=context.available_tasks,
            task_choice_memories=context.task_choice_memories,
            machine_state=local_machine_state_context(
                "No voice startup machine state provider"
            ),
            **client_kwargs(self._client_name),
        )

    async def task_name(self, task_id: str) -> str | None:
        database = await self._get_database()
        task = await database.tasks.get(task_id)
        if task is None:
            return None
        return task.content.name

    async def close(self) -> None:
        if self._database is not None and self._owns_database:
            await self._database.close()
            self._database = None

    async def _get_database(self) -> MemoryDatabase:
        if self._database is None:
            self._database = await open_memory_database()
        return self._database
