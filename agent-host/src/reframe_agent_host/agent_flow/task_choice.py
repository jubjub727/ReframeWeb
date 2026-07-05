from __future__ import annotations

from dataclasses import dataclass

from reframe_agent_host.baml_client import b, types
from reframe_agent_host.agent_flow.timestamps import timestamp_fields
from reframe_memory import MemoryDatabase, open_memory_database


@dataclass(frozen=True)
class TaskChoiceContext:
    session_conversations: list[types.ConversationHistory]
    session_memories: list[types.SessionMemoryContext]
    available_tasks: list[types.AvailableTask]
    task_choice_memories: list[types.TaskChoiceMemoryContext]


@dataclass
class TaskChoiceContextBuilder:
    database: MemoryDatabase
    session_id: str | None = None

    async def build(self) -> TaskChoiceContext:
        return TaskChoiceContext(
            session_conversations=await self._session_conversations(),
            session_memories=await self._session_memories(),
            available_tasks=await self._available_tasks(),
            task_choice_memories=await self._task_choice_memories(),
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

    async def _available_tasks(self) -> list[types.AvailableTask]:
        tasks = await self.database.tasks.search()
        return [
            types.AvailableTask(
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

    async def _task_choice_memories(self) -> list[types.TaskChoiceMemoryContext]:
        memories = await self.database.task_choice_memories.search()
        return [
            types.TaskChoiceMemoryContext(
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
        client_name: str | None = None,
    ) -> None:
        self._database = database
        self._owns_database = database is None
        self._session_id = session_id
        self._client_name = client_name

    async def choose_initial_task(
        self,
        current_user_request: str,
    ) -> types.TaskChoiceDecision:
        database = await self._get_database()
        context = await TaskChoiceContextBuilder(
            database=database,
            session_id=self._session_id,
        ).build()

        client = b.with_options(client=self._client_name) if self._client_name else b
        return await client.ChooseInitialTask(
            current_user_request=current_user_request,
            session_conversations=context.session_conversations,
            session_memories=context.session_memories,
            available_tasks=context.available_tasks,
            task_choice_memories=context.task_choice_memories,
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
            await self._database.apply_schema()
            await self._database.ensure_roots()
        return self._database
