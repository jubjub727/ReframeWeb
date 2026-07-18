from __future__ import annotations

from dataclasses import dataclass

from reframe_memory.schema import MEMORY_RELATIONS


@dataclass(frozen=True)
class BrowserView:
    key: str
    label: str
    root_ids: tuple[str, ...] = ()


VIEWS: tuple[BrowserView, ...] = (
    BrowserView("sessions", "Sessions", ("memory_root:sessions",)),
    BrowserView("conversations", "Conversations", ("memory_root:conversations",)),
    BrowserView("messages", "Messages"),
    BrowserView("tasks", "Tasks", ("memory_root:tasks",)),
    BrowserView(
        "memories",
        "Memories",
        (
            "memory_root:session_memories",
            "memory_root:task_choice_memories",
            "memory_root:conversation_evaluation_memories",
            "memory_root:search_depth_memories",
            "memory_root:relevance_memories",
            "memory_root:task_prompt_memories",
            "memory_root:user_preferences",
            "memory_root:filesystem_memories",
        ),
    ),
    BrowserView("providers", "Providers", ("memory_root:providers",)),
    BrowserView("raw", "Raw Records"),
)

TABLES: tuple[str, ...] = ("memory_root", "memory_node", *MEMORY_RELATIONS)


def view_for(key: str) -> BrowserView:
    for view in VIEWS:
        if view.key == key:
            return view
    return VIEWS[0]


def root_label(root_id: str, roots: dict[str, dict[str, object]]) -> str:
    root = roots.get(root_id)
    name = root.get("name") if root else None
    return str(name or root_id)
