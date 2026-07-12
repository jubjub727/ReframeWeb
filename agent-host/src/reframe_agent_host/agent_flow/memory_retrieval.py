from __future__ import annotations

from dataclasses import dataclass, field

from baml_sdk import memory_search as baml_memory_search
from reframe_memory import (
    MemoryDatabase,
    StringSearch,
    TagSearch,
    open_memory_database,
)
from reframe_memory.graph_retrieval import (
    GraphMemoryRetriever,
    GraphRetrievalRequest,
)
from reframe_memory.retrieval_terms import GraphSearchHints, TimestampBreadth
from reframe_memory.retrieved_context import RetrievedMemoryContext


@dataclass
class MemoryRetrievalPlanner:
    database: MemoryDatabase | None = None
    session_id: str | None = None
    _owns_database: bool = field(init=False)

    def __post_init__(self) -> None:
        self._owns_database = self.database is None

    async def retrieve(
        self,
        memory_search_hints: baml_memory_search.ConversationMemorySearchHints,
        search_depths: baml_memory_search.SearchDepthDecision,
    ) -> RetrievedMemoryContext:
        database = await self._get_database()
        retriever = GraphMemoryRetriever(
            database=database,
            current_session_id=self.session_id,
        )
        return await retriever.retrieve(
            GraphRetrievalRequest(
                hints=_search_hints(memory_search_hints),
                depths=_timestamp_breadths(search_depths),
            )
        )

    async def close(self) -> None:
        if self.database is not None and self._owns_database:
            await self.database.close()
            self.database = None

    async def _get_database(self) -> MemoryDatabase:
        if self.database is None:
            self.database = await open_memory_database()
        return self.database


def _search_hints(
    hints: baml_memory_search.ConversationMemorySearchHints,
) -> GraphSearchHints:
    return GraphSearchHints(
        tags=TagSearch.build(
            any_of=hints.tags.any_of,
            all_of=hints.tags.all_of,
            none_of=hints.tags.none_of,
        ),
        strings=StringSearch.build(
            contains=hints.strings.contains,
            equals=hints.strings.equals,
        ),
    )


def _timestamp_breadths(
    decision: baml_memory_search.SearchDepthDecision,
) -> dict[str, TimestampBreadth]:
    return {
        domain: TimestampBreadth.build(
            created_after=timestamps.created_after,
            updated_after=timestamps.updated_after,
            read_after=timestamps.read_after,
        )
        for domain, timestamps in decision.depths.items()
    }
