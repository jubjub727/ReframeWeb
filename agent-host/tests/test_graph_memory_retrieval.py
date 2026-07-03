import unittest
from datetime import UTC, datetime

from reframe_memory import (
    Conversation,
    ConversationMessage,
    GraphMemoryRetriever,
    GraphRetrievalRequest,
    GraphSearchHints,
    MemoryNode,
    MemoryTimestamps,
    Session,
    SessionMemory,
    StringSearch,
    TagSearch,
    Task,
    TimestampBreadth,
)
from reframe_memory.graph_retrieval import (
    PAST_CONVERSATION_CONTEXT_DOMAIN,
    TASK_CATALOG_DOMAIN,
)
from reframe_memory.retrieval_terms import candidate_matches


class GraphMemoryRetrievalTests(unittest.IsolatedAsyncioTestCase):
    def test_positive_hints_are_any_but_timestamps_are_all_required(self):
        hints = GraphSearchHints(
            tags=TagSearch.build(any_of=("workflow",), all_of=("visual",)),
            strings=StringSearch.build(contains=("compact view", "resize")),
        )
        breadth = _breadth(
            created_after="2026-01-01T00:00:00Z",
            updated_after="2026-01-01T00:00:00Z",
            read_after="2026-01-01T00:00:00Z",
        )

        tag_match = _task(
            "memory_node:task1",
            tags=("visual",),
            name="Open image editor",
            created_at=_dt("2026-02-01T00:00:00Z"),
            updated_at=_dt("2026-02-01T00:00:00Z"),
            read_at=None,
        )
        stale_created = _task(
            "memory_node:task2",
            tags=("workflow",),
            name="Resize image",
            created_at=_dt("2025-12-31T00:00:00Z"),
            updated_at=_dt("2026-02-01T00:00:00Z"),
            read_at=None,
        )
        old_read = _task(
            "memory_node:task3",
            tags=(),
            name="Resize image",
            created_at=_dt("2026-02-01T00:00:00Z"),
            updated_at=_dt("2026-02-01T00:00:00Z"),
            read_at=_dt("2025-12-31T00:00:00Z"),
        )

        self.assertTrue(
            candidate_matches(
                tag_match,
                fields=("name",),
                hints=hints,
                breadth=breadth,
            )
        )
        self.assertFalse(
            candidate_matches(
                stale_created,
                fields=("name",),
                hints=hints,
                breadth=breadth,
            )
        )
        self.assertFalse(
            candidate_matches(
                old_read,
                fields=("name",),
                hints=hints,
                breadth=breadth,
            )
        )

    async def test_child_candidates_hydrate_parent_wrappers(self):
        past_session = _session(
            "memory_node:session1",
            name="Old session",
            created_at=_dt("2025-01-01T00:00:00Z"),
            updated_at=_dt("2025-01-01T00:00:00Z"),
        )
        conversation = _conversation(
            "memory_node:conversation1",
            name="Old conversation",
            created_at=_dt("2025-01-01T00:00:00Z"),
            updated_at=_dt("2025-01-01T00:00:00Z"),
        )
        matching_message = _message(
            "memory_node:message1",
            content="Please always use compact view for this site.",
            created_at=_dt("2026-02-01T00:00:00Z"),
            updated_at=_dt("2026-02-01T00:00:00Z"),
        )
        matching_memory = _session_memory(
            "memory_node:memory1",
            title="Compact view preference",
            created_at=_dt("2026-02-01T00:00:00Z"),
            updated_at=_dt("2026-02-01T00:00:00Z"),
        )
        current_session = _session(
            "memory_node:current",
            name="Current session compact view",
            created_at=_dt("2026-02-01T00:00:00Z"),
            updated_at=_dt("2026-02-01T00:00:00Z"),
        )
        current_message = _message(
            "memory_node:currentmessage",
            content="compact view in current session",
            created_at=_dt("2026-02-01T00:00:00Z"),
            updated_at=_dt("2026-02-01T00:00:00Z"),
        )
        current_memory = _session_memory(
            "memory_node:currentmemory",
            title="Always show current preference",
            created_at=_dt("2025-01-01T00:00:00Z"),
            updated_at=_dt("2025-01-01T00:00:00Z"),
            tags=("excluded",),
        )
        database = _FakeDatabase(
            tasks=[],
            sessions=[past_session, current_session],
            conversations={
                past_session.id: [conversation],
                current_session.id: [
                    _conversation(
                        "memory_node:currentconversation",
                        name="Current conversation",
                    )
                ],
            },
            messages={
                conversation.id: [matching_message],
                "memory_node:currentconversation": [current_message],
            },
            memories={
                past_session.id: [matching_memory],
                current_session.id: [current_memory],
            },
        )

        result = await GraphMemoryRetriever(
            database,
            current_session_id=current_session.id,
        ).retrieve(
            GraphRetrievalRequest(
                hints=GraphSearchHints(
                    tags=TagSearch.build(none_of=("excluded",)),
                    strings=StringSearch.build(contains=("compact view",)),
                ),
                depths={
                    PAST_CONVERSATION_CONTEXT_DOMAIN: _breadth(
                        created_after="2026-01-01T00:00:00Z",
                        updated_after="2026-01-01T00:00:00Z",
                        read_after="2026-01-01T00:00:00Z",
                    )
                },
            )
        )

        sessions = result.past_conversation_context.sessions
        self.assertEqual([session.session.id for session in sessions], [past_session.id])
        self.assertFalse(sessions[0].matched)
        self.assertEqual(
            [item.conversation.id for item in sessions[0].conversations],
            [conversation.id],
        )
        self.assertFalse(sessions[0].conversations[0].matched)
        self.assertEqual(
            [message.id for message in sessions[0].conversations[0].messages],
            [matching_message.id],
        )
        self.assertEqual(
            [memory.id for memory in sessions[0].session_memories],
            [matching_memory.id],
        )
        self.assertEqual(
            [memory.id for memory in result.current_session_memories],
            [current_memory.id],
        )

    async def test_task_catalog_uses_rooted_task_candidates(self):
        matched_task = _task(
            "memory_node:task1",
            name="Resize an image",
            created_at=_dt("2026-02-01T00:00:00Z"),
            updated_at=_dt("2026-02-01T00:00:00Z"),
        )
        stale_task = _task(
            "memory_node:task2",
            name="Resize stale image",
            created_at=_dt("2026-02-01T00:00:00Z"),
            updated_at=_dt("2025-12-31T00:00:00Z"),
        )
        database = _FakeDatabase(
            tasks=[matched_task, stale_task],
            sessions=[],
            conversations={},
            messages={},
            memories={},
        )

        result = await GraphMemoryRetriever(database).retrieve(
            GraphRetrievalRequest(
                hints=GraphSearchHints(
                    strings=StringSearch.build(contains=("resize",))
                ),
                depths={
                    TASK_CATALOG_DOMAIN: _breadth(
                        created_after="2026-01-01T00:00:00Z",
                        updated_after="2026-01-01T00:00:00Z",
                        read_after="2026-01-01T00:00:00Z",
                    )
                },
            )
        )

        self.assertEqual(
            [task.id for task in result.task_catalog.tasks],
            [matched_task.id],
        )

    async def test_empty_positive_hints_do_not_match_historic_candidates(self):
        task = _task(
            "memory_node:task1",
            name="Resize an image",
            created_at=_dt("2026-02-01T00:00:00Z"),
            updated_at=_dt("2026-02-01T00:00:00Z"),
        )
        past_session = _session(
            "memory_node:session1",
            name="Past session",
            created_at=_dt("2026-02-01T00:00:00Z"),
            updated_at=_dt("2026-02-01T00:00:00Z"),
        )
        conversation = _conversation(
            "memory_node:conversation1",
            name="Past conversation",
            created_at=_dt("2026-02-01T00:00:00Z"),
            updated_at=_dt("2026-02-01T00:00:00Z"),
        )
        message = _message(
            "memory_node:message1",
            content="This would match only if empty hints meant everything.",
            created_at=_dt("2026-02-01T00:00:00Z"),
            updated_at=_dt("2026-02-01T00:00:00Z"),
        )
        current_session = _session("memory_node:current", name="Current session")
        current_memory = _session_memory(
            "memory_node:currentmemory",
            title="Always included",
        )
        database = _FakeDatabase(
            tasks=[task],
            sessions=[past_session, current_session],
            conversations={past_session.id: [conversation]},
            messages={conversation.id: [message]},
            memories={current_session.id: [current_memory]},
        )

        result = await GraphMemoryRetriever(
            database,
            current_session_id=current_session.id,
        ).retrieve(
            GraphRetrievalRequest(
                hints=GraphSearchHints(),
                depths={
                    TASK_CATALOG_DOMAIN: _breadth(
                        created_after="2026-01-01T00:00:00Z",
                        updated_after="2026-01-01T00:00:00Z",
                        read_after="2026-01-01T00:00:00Z",
                    ),
                    PAST_CONVERSATION_CONTEXT_DOMAIN: _breadth(
                        created_after="2026-01-01T00:00:00Z",
                        updated_after="2026-01-01T00:00:00Z",
                        read_after="2026-01-01T00:00:00Z",
                    ),
                },
            )
        )

        self.assertEqual(result.task_catalog.tasks, ())
        self.assertEqual(result.past_conversation_context.sessions, ())
        self.assertEqual(
            [memory.id for memory in result.current_session_memories],
            [current_memory.id],
        )


class _FakeDatabase:
    def __init__(self, *, tasks, sessions, conversations, messages, memories):
        self.tasks = _FakeTasks(tasks)
        self.sessions = _FakeSessions(sessions, conversations, memories)
        self.conversations = _FakeConversations(messages)


class _FakeTasks:
    def __init__(self, tasks):
        self._tasks = tasks

    async def search(self):
        return self._tasks


class _FakeSessions:
    def __init__(self, sessions, conversations, memories):
        self._sessions = sessions
        self._conversations = conversations
        self._memories = memories

    async def search(self):
        return self._sessions

    async def conversations_for(self, session_id):
        return self._conversations.get(session_id, [])

    async def memories_for(self, session_id):
        return self._memories.get(session_id, [])


class _FakeConversations:
    def __init__(self, messages):
        self._messages = messages

    async def messages_for(self, conversation_id):
        return self._messages.get(conversation_id, [])


def _task(
    node_id,
    *,
    name,
    tags=(),
    created_at=None,
    updated_at=None,
    read_at=None,
):
    return _node(
        node_id,
        tags=tags,
        content=Task(
            name=name,
            description="",
            input="",
            output="",
            prompt="",
            provider_id="memory_node:provider",
        ),
        created_at=created_at,
        updated_at=updated_at,
        read_at=read_at,
    )


def _session(node_id, *, name, created_at=None, updated_at=None):
    return _node(
        node_id,
        content=Session(name=name),
        created_at=created_at,
        updated_at=updated_at,
    )


def _conversation(node_id, *, name, created_at=None, updated_at=None):
    return _node(
        node_id,
        content=Conversation(name=name),
        created_at=created_at,
        updated_at=updated_at,
    )


def _message(node_id, *, content, created_at=None, updated_at=None):
    return _node(
        node_id,
        content=ConversationMessage(role="human", content=content),
        created_at=created_at,
        updated_at=updated_at,
    )


def _session_memory(node_id, *, title, created_at=None, updated_at=None, tags=()):
    return _node(
        node_id,
        tags=tags,
        content=SessionMemory(title=title, description=""),
        created_at=created_at,
        updated_at=updated_at,
    )


def _node(
    node_id,
    *,
    content,
    tags=(),
    created_at=None,
    updated_at=None,
    read_at=None,
):
    created_at = created_at or _dt("2026-02-01T00:00:00Z")
    updated_at = updated_at or created_at
    return MemoryNode(
        id=node_id,
        tags=tuple(tags),
        timestamps=MemoryTimestamps(
            created_at=created_at,
            updated_at=updated_at,
            read_at=read_at,
        ),
        content=content,
    )


def _breadth(*, created_after, updated_after, read_after):
    return TimestampBreadth.build(
        created_after=created_after,
        updated_after=updated_after,
        read_after=read_after,
    )


def _dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


if __name__ == "__main__":
    unittest.main()
