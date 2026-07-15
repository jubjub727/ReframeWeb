from __future__ import annotations

from baml_sdk import turn_context as baml_turn_context
from baml_sdk import memory as baml_memory
from baml_sdk import task_catalog as baml_task_catalog
from baml_sdk import task as baml_task
from reframe_agent_host.agent_flow.timestamps import timestamp_fields
from reframe_memory import MemoryDatabase


async def available_tasks(
    database: MemoryDatabase,
) -> list[baml_task_catalog.AvailableTask]:
    tasks = await database.tasks.search()
    providers = (
        {
            provider.id: provider.content.model_id
            for provider in await database.providers.search()
        }
        if tasks
        else {}
    )
    return [
        baml_task_catalog.AvailableTask(
            id=task.id,
            name=task.content.name,
            description=task.content.description,
            input=task.content.input,
            output=task.content.output,
            prompt=task.content.prompt,
            provider_id=task.content.provider_id,
            model_id=_task_model_id(task.id, task.content.provider_id, providers),
            **timestamp_fields(task),
        )
        for task in tasks
    ]


def _task_model_id(task_id: str, provider_id: str, providers: dict[str, str]) -> str:
    model_id = providers.get(provider_id)
    if not model_id:
        raise ValueError(
            f"task {task_id} has no provider model: {provider_id}"
        )
    return model_id


async def user_preferences(
    database: MemoryDatabase,
) -> list[baml_turn_context.UserPreferenceMemoryContext]:
    return [
        baml_turn_context.UserPreferenceMemoryContext(
            id=memory.id,
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in await database.user_preferences.search()
    ]


async def task_choice_memories(
    database: MemoryDatabase,
) -> list[baml_task.TaskChoiceMemoryContext]:
    return [
        baml_task.TaskChoiceMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in await database.task_choice_memories.search()
    ]


async def conversation_evaluation_memories(database: MemoryDatabase):
    return [
        baml_memory.ConversationEvaluationMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in await database.conversation_evaluation_memories.search()
    ]


async def search_depth_memories(database: MemoryDatabase):
    return [
        baml_memory.SearchDepthMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in await database.search_depth_memories.search()
    ]


async def relevance_memories(database: MemoryDatabase):
    return [
        baml_memory.RelevanceMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in await database.relevance_memories.search()
    ]


async def task_prompt_memories(database: MemoryDatabase):
    return [
        baml_task.TaskPromptMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in await database.task_prompt_memories.search()
    ]
