from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, ClassVar, Generic, TypeAlias, TypeVar

from reframe_memory.models import (
    ContextMemory,
    ConversationEvaluationMemory,
    RelevanceMemory,
    SearchDepthMemory,
    TaskChoiceMemory,
    TaskPromptMemory,
    UserPreferenceMemory,
)
from reframe_memory.records import memory_node_from_record
from reframe_memory.query_results import first_record as _first_record
from reframe_memory.query_results import records as _records
from reframe_memory.search import (
    MemoryNodeSearch,
    StringSearch,
    TagSearch,
    build_memory_node_where,
)

if TYPE_CHECKING:
    from reframe_memory.database import MemoryDatabase
    from reframe_memory.models import MemoryNode


ContentT = TypeVar("ContentT", bound=ContextMemory)


@dataclass(frozen=True)
class ContextMemorySearch:
    tags: TagSearch = TagSearch()
    strings: StringSearch = StringSearch()
    titles: tuple[str, ...] = ()
    descriptions: tuple[str, ...] = ()

    @classmethod
    def build(
        cls,
        *,
        tags: TagSearch | None = None,
        strings: StringSearch | None = None,
        titles: Sequence[str] = (),
        descriptions: Sequence[str] = (),
    ) -> ContextMemorySearch:
        return cls(
            tags=tags or TagSearch(),
            strings=strings or StringSearch(),
            titles=tuple(titles),
            descriptions=tuple(descriptions),
        )

    def as_memory_node_search(self) -> MemoryNodeSearch:
        return MemoryNodeSearch(
            tags=self.tags,
            strings=self.strings,
            string_fields=("title", "description"),
            content_contains={
                "title": self.titles,
                "description": self.descriptions,
            },
        )


@dataclass(frozen=True)
class ContextMemoryCollection(Generic[ContentT]):
    root_id: str
    root_name: str
    root_description: str
    content_type: type[ContentT]


@dataclass
class ContextMemoryStore(Generic[ContentT]):
    database: MemoryDatabase
    collection: ClassVar[ContextMemoryCollection]

    async def ensure_root(self) -> None:
        await self.database.query(
            f"""
            UPSERT {self.collection.root_id} SET
                name = $name,
                description = $description;
            """,
            {
                "name": self.collection.root_name,
                "description": self.collection.root_description,
            },
        )

    async def create(
        self,
        memory: ContentT,
        tags: Sequence[str] = (),
    ) -> MemoryNode[ContentT]:
        result = await self.database.query(
            """
            CREATE memory_node SET
                tags = $tags,
                content = $content,
                created_at = time::now(),
                updated_at = time::now(),
                read_at = NONE;
            """,
            {
                "tags": list(dict.fromkeys(tag.strip() for tag in tags if tag.strip())),
                "content": asdict(memory),
            },
        )
        node = _first_record(result)
        await self.database.query(
            f"RELATE {self.collection.root_id}->contains->$node_id;",
            {"node_id": node["id"]},
        )
        return self._node_from_record(node)

    async def search(
        self,
        search: ContextMemorySearch | None = None,
        *,
        mark_read: bool = True,
    ) -> list[MemoryNode[ContentT]]:
        node_search = search.as_memory_node_search() if search else None
        parts = build_memory_node_where(node_search)
        result = await self.database.query(
            f"""
            SELECT * FROM {self.collection.root_id}->contains->memory_node
            {parts.where_sql}
            ORDER BY updated_at DESC, created_at DESC;
            """,
            parts.variables,
        )
        records = _records(result)
        if mark_read:
            records = await self.database.mark_records_read(records)
        return [self._node_from_record(record) for record in records]

    def _node_from_record(self, record: Mapping[str, object]):
        return memory_node_from_record(record, self._parse_content)

    def _parse_content(self, content: Mapping[str, object]) -> ContentT:
        return self.collection.content_type(
            title=str(content["title"]),
            description=str(content["description"]),
        )


TASK_CHOICE_MEMORIES_ROOT_ID = "memory_root:task_choice_memories"
CONVERSATION_EVALUATION_MEMORIES_ROOT_ID = (
    "memory_root:conversation_evaluation_memories"
)
SEARCH_DEPTH_MEMORIES_ROOT_ID = "memory_root:search_depth_memories"
RELEVANCE_MEMORIES_ROOT_ID = "memory_root:relevance_memories"
TASK_PROMPT_MEMORIES_ROOT_ID = "memory_root:task_prompt_memories"
USER_PREFERENCES_ROOT_ID = "memory_root:user_preferences"


class TaskChoiceMemoryStore(ContextMemoryStore[TaskChoiceMemory]):
    collection = ContextMemoryCollection(
        TASK_CHOICE_MEMORIES_ROOT_ID,
        "Task Choice Memories",
        "Nodes connected from this root guide the task-choice prompt step.",
        TaskChoiceMemory,
    )


class ConversationEvaluationMemoryStore(
    ContextMemoryStore[ConversationEvaluationMemory]
):
    collection = ContextMemoryCollection(
        CONVERSATION_EVALUATION_MEMORIES_ROOT_ID,
        "Conversation Evaluation Memories",
        "Nodes connected from this root guide conversation evaluation.",
        ConversationEvaluationMemory,
    )


class SearchDepthMemoryStore(ContextMemoryStore[SearchDepthMemory]):
    collection = ContextMemoryCollection(
        SEARCH_DEPTH_MEMORIES_ROOT_ID,
        "Search Depth Memories",
        "Nodes connected from this root guide memory search depth selection.",
        SearchDepthMemory,
    )


class RelevanceMemoryStore(ContextMemoryStore[RelevanceMemory]):
    collection = ContextMemoryCollection(
        RELEVANCE_MEMORIES_ROOT_ID,
        "Relevance Memories",
        "Nodes connected from this root guide memory relevance selection.",
        RelevanceMemory,
    )


class TaskPromptMemoryStore(ContextMemoryStore[TaskPromptMemory]):
    collection = ContextMemoryCollection(
        TASK_PROMPT_MEMORIES_ROOT_ID,
        "Task Prompt Memories",
        "Nodes connected from this root guide task-prompt composition.",
        TaskPromptMemory,
    )


class UserPreferenceMemoryStore(ContextMemoryStore[UserPreferenceMemory]):
    collection = ContextMemoryCollection(
        USER_PREFERENCES_ROOT_ID,
        "User Preferences",
        "Nodes connected from this root are durable global user preferences.",
        UserPreferenceMemory,
    )


TaskChoiceMemorySearch: TypeAlias = ContextMemorySearch
ConversationEvaluationMemorySearch: TypeAlias = ContextMemorySearch
SearchDepthMemorySearch: TypeAlias = ContextMemorySearch
RelevanceMemorySearch: TypeAlias = ContextMemorySearch
TaskPromptMemorySearch: TypeAlias = ContextMemorySearch
UserPreferenceMemorySearch: TypeAlias = ContextMemorySearch

