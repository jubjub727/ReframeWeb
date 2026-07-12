from __future__ import annotations

from baml_sdk import context as baml_context
from baml_sdk import memory_search as baml_memory_search
from baml_sdk import memory_selection as baml_memory_selection
from baml_sdk import task_prompt as baml_task_prompt
from baml_sdk import task_routing as baml_task_routing
from reframe_agent_host.agent_flow.timestamps import timestamp_fields
from reframe_memory import MemoryDatabase


async def available_tasks(
    database: MemoryDatabase,
) -> list[baml_task_routing.AvailableTask]:
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
        for task in await database.tasks.search()
    ]


async def user_preferences(
    database: MemoryDatabase,
) -> list[baml_context.UserPreferenceMemoryContext]:
    return [
        baml_context.UserPreferenceMemoryContext(
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
) -> list[baml_task_routing.TaskChoiceMemoryContext]:
    return [
        baml_task_routing.TaskChoiceMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in await database.task_choice_memories.search()
    ]


async def conversation_evaluation_memories(database: MemoryDatabase):
    return [
        baml_memory_search.ConversationEvaluationMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in await database.conversation_evaluation_memories.search()
    ]


async def search_depth_memories(database: MemoryDatabase):
    return [
        baml_memory_search.SearchDepthMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in await database.search_depth_memories.search()
    ]


async def relevance_memories(database: MemoryDatabase):
    return [
        baml_memory_selection.RelevanceMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in await database.relevance_memories.search()
    ]


async def task_prompt_memories(database: MemoryDatabase):
    return [
        baml_task_prompt.TaskPromptMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in await database.task_prompt_memories.search()
    ]
