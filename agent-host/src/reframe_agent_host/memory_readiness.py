from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from reframe_memory.context_memories import (
    CONVERSATION_EVALUATION_MEMORIES_ROOT_ID,
    RELEVANCE_MEMORIES_ROOT_ID,
    SEARCH_DEPTH_MEMORIES_ROOT_ID,
    TASK_CHOICE_MEMORIES_ROOT_ID,
    TASK_PROMPT_MEMORIES_ROOT_ID,
    USER_PREFERENCES_ROOT_ID,
)
from reframe_memory.conversations import CONVERSATIONS_ROOT_ID
from reframe_memory.providers import PROVIDERS_ROOT_ID
from reframe_memory.session_memories import SESSION_MEMORIES_ROOT_ID
from reframe_memory.sessions import SESSIONS_ROOT_ID
from reframe_memory.tasks import TASKS_ROOT_ID


class MemoryReadinessError(RuntimeError):
    pass


ROOT_IDS = (
    PROVIDERS_ROOT_ID,
    TASKS_ROOT_ID,
    SESSIONS_ROOT_ID,
    CONVERSATIONS_ROOT_ID,
    SESSION_MEMORIES_ROOT_ID,
    TASK_CHOICE_MEMORIES_ROOT_ID,
    CONVERSATION_EVALUATION_MEMORIES_ROOT_ID,
    SEARCH_DEPTH_MEMORIES_ROOT_ID,
    RELEVANCE_MEMORIES_ROOT_ID,
    TASK_PROMPT_MEMORIES_ROOT_ID,
    USER_PREFERENCES_ROOT_ID,
)


async def require_memory_ready(
    database,
    *,
    require_task_catalog: bool = False,
) -> None:
    try:
        missing_roots = await _missing_roots(database)
    except Exception as error:
        raise MemoryReadinessError(
            "memory database could not be checked; run "
            "`uv run reframe-agent-host memory-setup` and try again. "
            f"Original error: {type(error).__name__}: {error}"
        ) from error

    if missing_roots:
        raise MemoryReadinessError(
            "memory database is not initialized; missing roots: "
            f"{', '.join(_root_name(root_id) for root_id in missing_roots)}. "
            "Run `uv run reframe-agent-host memory-setup`."
        )

    if not require_task_catalog:
        return

    try:
        missing_catalog = []
        if not await database.providers.search(mark_read=False):
            missing_catalog.append("providers")
        if not await database.tasks.search(mark_read=False):
            missing_catalog.append("tasks")
    except Exception as error:
        raise MemoryReadinessError(
            "memory task-choice data could not be checked; run "
            "`uv run reframe-agent-host seed-opencode-go-providers` and "
            "`uv run reframe-agent-host seed-core-tasks`, then try again. "
            f"Original error: {type(error).__name__}: {error}"
        ) from error

    if missing_catalog:
        raise MemoryReadinessError(
            "memory database is missing seeded task-choice data: "
            f"{', '.join(missing_catalog)}. Run "
            "`uv run reframe-agent-host seed-opencode-go-providers` and "
            "`uv run reframe-agent-host seed-core-tasks`."
        )


async def _missing_roots(database) -> list[str]:
    missing = []
    for root_id in ROOT_IDS:
        result = await database.query(f"SELECT id FROM {root_id} LIMIT 1;")
        if not _records(result):
            missing.append(root_id)
    return missing


def _root_name(root_id: str) -> str:
    return root_id.split(":", 1)[-1]


def _records(result: Any) -> list[Mapping[str, Any]]:
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, Mapping)]
