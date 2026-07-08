import unittest
from datetime import UTC, datetime

from reframe_agent_host.agent_flow.relevance_candidates import (
    candidate_contexts,
    filter_retrieved_memories,
)
import baml_sdk as types
from reframe_memory import (
    Conversation,
    ConversationMessage,
    MemoryNode,
    MemoryTimestamps,
    Session,
    SessionMemory,
    Task,
)
from reframe_memory.retrieved_context import (
    RetrievedConversation,
    RetrievedMemoryContext,
    RetrievedPastConversationContext,
    RetrievedSessionContext,
    RetrievedTaskCatalog,
)


class MemoryRelevanceTests(unittest.TestCase):
    def test_candidate_contexts_flatten_all_retrieved_nodes(self):
        memories = _retrieved_memories()

        candidates = candidate_contexts(memories, "memory_node:current")

        self.assertEqual(
            [candidate.id for candidate in candidates],
            [
                "memory_node:task1",
                "memory_node:currentmemory",
                "memory_node:session1",
                "memory_node:pastmemory",
                "memory_node:conversation1",
                "memory_node:message1",
                "memory_node:message2",
            ],
        )
        message = candidates[-1]
        self.assertEqual(message.kind, "past_conversation_message")
        self.assertEqual(message.parent_session_id, "memory_node:session1")
        self.assertEqual(message.parent_conversation_id, "memory_node:conversation1")

    def test_candidate_contexts_marks_current_session_conversation_kinds(self):
        session = _session("memory_node:current", name="Current session")
        conversation = _conversation(
            "memory_node:conversationcurrent",
            name="Current conversation",
        )
        message = _message(
            "memory_node:messagecurrent",
            content="This is from the current session.",
        )
        sibling = _message(
            "memory_node:messagesibling",
            content="Surrounding context from the current session.",
        )
        memories = RetrievedMemoryContext(
            past_conversation_context=RetrievedPastConversationContext(
                sessions=(
                    RetrievedSessionContext(
                        session=session,
                        matched=True,
                        conversations=(
                            RetrievedConversation(
                                conversation=conversation,
                                matched=False,
                                messages=(message, sibling),
                                matched_message_ids=(message.id,),
                            ),
                        ),
                    ),
                )
            )
        )

        candidates = candidate_contexts(memories, "memory_node:current")

        self.assertEqual(
            [
                (candidate.id, candidate.kind, candidate.retrieval_matched)
                for candidate in candidates
            ],
            [
                ("memory_node:current", "current_session", True),
                ("memory_node:conversationcurrent", "current_conversation", False),
                ("memory_node:messagecurrent", "current_conversation_message", True),
                ("memory_node:messagesibling", "current_conversation_message", False),
            ],
        )

    def test_candidate_contexts_include_all_user_preferences(self):
        candidates = candidate_contexts(
            RetrievedMemoryContext(),
            user_preferences=[
                types.UserPreferenceMemoryContext(
                    id="memory_node:pref1",
                    title="Interface density",
                    description="Prefer compact, information-dense interfaces.",
                    tags=["compact", "ui"],
                    created_at="2026-02-01T00:00:00Z",
                    updated_at="2026-02-01T00:00:00Z",
                    read_at="NONE",
                ),
                types.UserPreferenceMemoryContext(
                    id="memory_node:pref2",
                    title="Reply style",
                    description="Keep CLI output terse.",
                    tags=["cli"],
                    created_at="2026-02-01T00:00:00Z",
                    updated_at="2026-02-01T00:00:00Z",
                    read_at="NONE",
                ),
            ],
        )

        self.assertEqual(
            [
                (
                    candidate.id,
                    candidate.kind,
                    candidate.title,
                    candidate.retrieval_matched,
                )
                for candidate in candidates
            ],
            [
                (
                    "memory_node:pref1",
                    "user_preference",
                    "Interface density",
                    False,
                ),
                ("memory_node:pref2", "user_preference", "Reply style", False),
            ],
        )

    def test_filter_keeps_child_memories_with_parent_wrappers(self):
        memories = _retrieved_memories()

        filtered = filter_retrieved_memories(
            memories,
            types.RelevantMemoryDecision(
                kept_memory_ids=[
                    "memory_node:message1",
                    "memory_node:currentmemory",
                    "memory_node:missing",
                ],
                candidate_memory=None,
            ),
        )

        self.assertEqual(filtered.task_catalog.tasks, ())
        self.assertEqual(
            [memory.id for memory in filtered.current_session_memories],
            ["memory_node:currentmemory"],
        )
        sessions = filtered.past_conversation_context.sessions
        self.assertEqual([session.session.id for session in sessions], ["memory_node:session1"])
        self.assertEqual(sessions[0].session_memories, ())
        conversations = sessions[0].conversations
        self.assertEqual(
            [conversation.conversation.id for conversation in conversations],
            ["memory_node:conversation1"],
        )
        self.assertEqual(
            [message.id for message in conversations[0].messages],
            ["memory_node:message1"],
        )

    def test_filter_keeps_parent_session_for_selected_session_memory(self):
        filtered = filter_retrieved_memories(
            _retrieved_memories(),
            types.RelevantMemoryDecision(
                kept_memory_ids=["memory_node:pastmemory"],
                candidate_memory=None,
            ),
        )

        sessions = filtered.past_conversation_context.sessions
        self.assertEqual([session.session.id for session in sessions], ["memory_node:session1"])
        self.assertEqual(
            [memory.id for memory in sessions[0].session_memories],
            ["memory_node:pastmemory"],
        )
        self.assertEqual(sessions[0].conversations, ())

    def test_filter_can_keep_explicit_wrapper_without_children(self):
        filtered = filter_retrieved_memories(
            _retrieved_memories(),
            types.RelevantMemoryDecision(
                kept_memory_ids=["memory_node:conversation1"],
                candidate_memory=None,
            ),
        )

        sessions = filtered.past_conversation_context.sessions
        self.assertEqual([session.session.id for session in sessions], ["memory_node:session1"])
        self.assertEqual(
            [conversation.conversation.id for conversation in sessions[0].conversations],
            ["memory_node:conversation1"],
        )
        self.assertEqual(sessions[0].conversations[0].messages, ())

    def test_relevance_decision_has_optional_candidate_memory(self):
        decision = types.RelevantMemoryDecision(
            kept_memory_ids=["memory_node:message1"],
            candidate_memory=None,
        )

        self.assertEqual(
            decision.model_dump(mode="json"),
            {
                "kept_memory_ids": ["memory_node:message1"],
                "candidate_memory": None,
            },
        )


def _retrieved_memories():
    task = _task("memory_node:task1", name="Prepare visual panel")
    current_memory = _session_memory(
        "memory_node:currentmemory",
        title="Current compact preference",
    )
    session = _session("memory_node:session1", name="Old Hacker News session")
    conversation = _conversation(
        "memory_node:conversation1",
        name="HN layout conversation",
    )
    message = _message(
        "memory_node:message1",
        content="Please keep Hacker News compact like last time.",
    )
    sibling = _message(
        "memory_node:message2",
        content="The layout should still keep the story title visible.",
    )
    past_memory = _session_memory(
        "memory_node:pastmemory",
        title="Hacker News compact rows",
    )
    return RetrievedMemoryContext(
        task_catalog=RetrievedTaskCatalog(tasks=(task,)),
        past_conversation_context=RetrievedPastConversationContext(
            sessions=(
                RetrievedSessionContext(
                    session=session,
                    matched=False,
                    conversations=(
                        RetrievedConversation(
                            conversation=conversation,
                            matched=False,
                            messages=(message, sibling),
                            matched_message_ids=(message.id,),
                        ),
                    ),
                    session_memories=(past_memory,),
                ),
            )
        ),
        current_session_memories=(current_memory,),
    )


def _task(node_id, *, name):
    return _node(
        node_id,
        content=Task(
            name=name,
            description="Task description",
            input="Task input",
            output="Task output",
            prompt="Task prompt",
            provider_id="memory_node:provider",
        ),
    )


def _session(node_id, *, name):
    return _node(node_id, content=Session(name=name))


def _conversation(node_id, *, name):
    return _node(node_id, content=Conversation(name=name))


def _message(node_id, *, content):
    return _node(node_id, content=ConversationMessage(role="human", content=content))


def _session_memory(node_id, *, title):
    return _node(
        node_id,
        content=SessionMemory(title=title, description="Memory description"),
    )


def _node(node_id, *, content, tags=()):
    created_at = _dt("2026-02-01T00:00:00Z")
    return MemoryNode(
        id=node_id,
        tags=tuple(tags),
        timestamps=MemoryTimestamps(
            created_at=created_at,
            updated_at=created_at,
            read_at=None,
        ),
        content=content,
    )


def _dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


if __name__ == "__main__":
    unittest.main()
