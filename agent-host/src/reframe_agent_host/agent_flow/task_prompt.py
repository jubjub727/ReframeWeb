from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from reframe_agent_host.agent_flow.timestamps import timestamp_fields
from reframe_agent_host.agent_flow.session_context import current_conversation_history
import baml_sdk as baml
import baml_sdk as types
from reframe_agent_host.agent_flow.baml_clients import client_kwargs
from reframe_memory import MemoryDatabase, TaskNode, open_memory_database
from reframe_memory.retrieved_context import RetrievedMemoryContext


@dataclass(frozen=True)
class TaskPromptContext:
    current_conversation: types.ConversationHistory | None
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
    conversation_id: str | None = None

    async def build(self) -> TaskPromptContext:
        return TaskPromptContext(
            current_conversation=await self._current_conversation(),
            session_memories=await self._session_memories(),
            selected_task=await self._selected_task(),
            selected_memories=selected_memory_contexts(
                self.selected_memories,
                self.selected_memory_ids,
                current_session_id=self.session_id,
            ),
            task_prompt_memories=await self._task_prompt_memories(),
        )

    async def _current_conversation(self) -> types.ConversationHistory | None:
        return await current_conversation_history(
            self.database,
            self.session_id,
            self.conversation_id,
        )

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
        conversation_id: str | None = None,
        client_name: str | None = None,
    ) -> None:
        self._database = database
        self._owns_database = database is None
        self._session_id = session_id
        self._conversation_id = conversation_id
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
            conversation_id=self._conversation_id,
            selected_task_id=selected_task_id,
            selected_memories=selected_memories,
            selected_memory_ids=selected_memory_ids,
        ).build()

        composition = await baml.ComposeTaskInput_async(
            current_user_request=current_user_request,
            current_conversation=context.current_conversation,
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
    current_session_id: str | None = None,
) -> list[types.TaskPromptSelectedMemoryContext]:
    selected_ids = set(selected_memory_ids)
    contexts: list[types.TaskPromptSelectedMemoryContext] = []
    contexts.extend(_task_context(task) for task in memories.task_catalog.tasks)
    contexts.extend(
        _session_memory_context(memory)
        for memory in memories.current_session_memories
    )
    for session in memories.past_conversation_context.sessions:
        is_current_session = _is_current_session(session, current_session_id)
        if _include_session_context(session, selected_ids):
            contexts.append(_session_context(session, is_current_session))
        contexts.extend(
            _session_memory_context(memory)
            for memory in session.session_memories
        )
        for conversation in session.conversations:
            if _include_conversation_context(conversation, selected_ids):
                contexts.append(
                    _conversation_context(session, conversation, is_current_session)
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


def _include_session_context(session, selected_ids: set[str]) -> bool:
    return (
        session.matched
        or session.session.id in selected_ids
        or bool(session.session_memories)
        or bool(session.conversations)
    )


def _include_conversation_context(
    conversation,
    selected_ids: set[str],
) -> bool:
    return (
        conversation.matched
        or conversation.conversation.id in selected_ids
        or bool(conversation.messages)
    )


def _is_current_session(session, current_session_id: str | None) -> bool:
    return current_session_id is not None and session.session.id == current_session_id


def _task_context(task: TaskNode) -> types.TaskPromptSelectedMemoryContext:
    return _context(
        title=task.content.name,
        description=task.content.description,
        node=task,
    )


def _session_context(
    session,
    is_current_session: bool,
) -> types.TaskPromptSelectedMemoryContext:
    prefix = "Current" if is_current_session else "Past"
    return _context(
        title=f"{prefix} session: {session.session.content.name}",
        description="Parent session for selected remembered context.",
        node=session.session,
    )


def _conversation_context(
    session,
    conversation,
    is_current_session: bool,
) -> types.TaskPromptSelectedMemoryContext:
    prefix = "Current" if is_current_session else "Past"
    return _context(
        title=f"{prefix} conversation: {conversation.conversation.content.name}",
        description=(
            "Parent conversation for selected remembered context "
            f"in session: {session.session.content.name}."
        ),
        node=conversation.conversation,
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
