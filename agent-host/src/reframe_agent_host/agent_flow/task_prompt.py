from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from reframe_agent_host.agent_flow.timestamps import timestamp_fields
import baml_sdk as baml
import baml_sdk as types
from reframe_agent_host.agent_flow.baml_clients import client_kwargs
from reframe_memory import MemoryDatabase, TaskNode, open_memory_database
from reframe_memory.retrieved_context import RetrievedMemoryContext


@dataclass(frozen=True)
class TaskPromptContext:
    session_conversations: list[types.ConversationHistory]
    session_memories: list[types.SessionMemoryContext]
    selected_task: types.SelectedTaskContext
    selected_memories: list[types.TaskPromptSelectedMemoryContext]
    task_prompt_memories: list[types.TaskPromptMemoryContext]


@dataclass
class TaskPromptContextBuilder:
    database: MemoryDatabase
    selected_task_id: str
    selected_memories: RetrievedMemoryContext
    selected_memory_ids: Collection[str] = ()
    session_id: str | None = None

    async def build(self) -> TaskPromptContext:
        return TaskPromptContext(
            session_conversations=await self._session_conversations(),
            session_memories=await self._session_memories(),
            selected_task=await self._selected_task(),
            selected_memories=selected_memory_contexts(
                self.selected_memories,
                self.selected_memory_ids,
            ),
            task_prompt_memories=await self._task_prompt_memories(),
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

    async def _task_prompt_memories(self) -> list[types.TaskPromptMemoryContext]:
        memories = await self.database.task_prompt_memories.search()
        return [
            types.TaskPromptMemoryContext(
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                **timestamp_fields(memory),
            )
            for memory in memories
        ]


class TaskPromptPlanner:
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

    async def generate_task_prompt(
        self,
        current_user_request: str,
        selected_task_id: str,
        selected_memories: RetrievedMemoryContext,
        selected_memory_ids: Collection[str] = (),
    ) -> types.TaskPromptDecision:
        database = await self._get_database()
        context = await TaskPromptContextBuilder(
            database=database,
            session_id=self._session_id,
            selected_task_id=selected_task_id,
            selected_memories=selected_memories,
            selected_memory_ids=selected_memory_ids,
        ).build()

        composition = await baml.GenerateTaskPrompt_async(
            current_user_request=current_user_request,
            session_conversations=context.session_conversations,
            session_memories=context.session_memories,
            selected_task=context.selected_task,
            selected_memories=context.selected_memories,
            task_prompt_memories=context.task_prompt_memories,
            **client_kwargs(self._client_name),
        )
        return build_task_prompt_decision(context.selected_task.prompt, composition)

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


def selected_memory_contexts(
    memories: RetrievedMemoryContext,
    selected_memory_ids: Collection[str] = (),
) -> list[types.TaskPromptSelectedMemoryContext]:
    selected_ids = set(selected_memory_ids)
    contexts: list[types.TaskPromptSelectedMemoryContext] = []
    contexts.extend(_task_context(task) for task in memories.task_catalog.tasks)
    contexts.extend(
        _session_memory_context(memory)
        for memory in memories.current_session_memories
    )
    for session in memories.past_conversation_context.sessions:
        if session.matched or session.session.id in selected_ids:
            contexts.append(
                _context(
                    title=f"Past session: {session.session.content.name}",
                    description="A past session was selected as relevant.",
                    node=session.session,
                )
            )
        contexts.extend(
            _session_memory_context(memory)
            for memory in session.session_memories
        )
        for conversation in session.conversations:
            if conversation.matched or conversation.conversation.id in selected_ids:
                contexts.append(
                    _context(
                        title=f"Past conversation: {conversation.conversation.content.name}",
                        description="A past conversation was selected as relevant.",
                        node=conversation.conversation,
                    )
                )
            contexts.extend(_message_context(message) for message in conversation.messages)
    return contexts


def build_task_prompt_decision(
    selected_task_prompt: str,
    composition: types.TaskPromptComposition,
) -> types.TaskPromptDecision:
    return types.TaskPromptDecision(
        full_task_prompt=compose_full_task_prompt(
            selected_task_prompt,
            composition.task_input,
        ),
        candidate_memory=composition.candidate_memory,
    )


def compose_full_task_prompt(selected_task_prompt: str, task_input: str) -> str:
    return f"Task:\n{selected_task_prompt}\n\nInput:\n{task_input}"


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


def _task_context(task: TaskNode) -> types.TaskPromptSelectedMemoryContext:
    return _context(
        title=task.content.name,
        description=task.content.description,
        node=task,
    )


def _session_memory_context(memory) -> types.TaskPromptSelectedMemoryContext:
    return _context(
        title=memory.content.title,
        description=memory.content.description,
        node=memory,
    )


def _message_context(message) -> types.TaskPromptSelectedMemoryContext:
    return _context(
        title=f"{message.content.role} message",
        description=message.content.content,
        node=message,
    )


def _context(
    *,
    title: str,
    description: str,
    node,
) -> types.TaskPromptSelectedMemoryContext:
    return types.TaskPromptSelectedMemoryContext(
        title=title,
        description=description,
        tags=list(node.tags),
        **timestamp_fields(node),
    )
