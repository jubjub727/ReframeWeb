import unittest
from datetime import UTC, datetime

from reframe_agent_host.agent_flow.task_choice import TaskChoiceContextBuilder
from reframe_agent_host.commands.parser import build_parser
from reframe_memory import (
    Conversation,
    ConversationMessage,
    MemoryNode,
    MemoryTimestamps,
)


class TaskChoiceContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_context_uses_current_conversation_history(self):
        database = FakeDatabase()

        context = await TaskChoiceContextBuilder(
            database=database,
            session_id="memory_node:session",
            conversation_id="memory_node:current",
        ).build()

        self.assertIsNotNone(context.current_conversation)
        self.assertEqual(context.current_conversation.id, "memory_node:current")
        rendered = "\n".join(
            message.content
            for message in context.current_conversation.messages
        )
        self.assertIn("Current conversation message.", rendered)
        self.assertNotIn("Previous conversation message.", rendered)

    async def test_context_without_current_conversation_has_no_history(self):
        context = await TaskChoiceContextBuilder(
            database=FakeDatabase(),
            session_id="memory_node:session",
        ).build()

        self.assertIsNone(context.current_conversation)

    def test_choose_task_accepts_current_conversation_id(self):
        args = build_parser().parse_args(
            [
                "choose-task",
                "do this",
                "--session-id",
                "memory_node:session",
                "--conversation-id",
                "memory_node:current",
            ]
        )

        self.assertEqual(args.session_id, "memory_node:session")
        self.assertEqual(args.conversation_id, "memory_node:current")


class FakeDatabase:
    def __init__(self):
        self.sessions = FakeSessions(
            [
                _conversation("memory_node:current", "Current conversation"),
                _conversation("memory_node:previous", "Previous conversation"),
            ]
        )
        self.conversations = FakeConversations(
            {
                "memory_node:current": [
                    _message("memory_node:message1", "Current conversation message.")
                ],
                "memory_node:previous": [
                    _message("memory_node:message2", "Previous conversation message.")
                ],
            }
        )
        self.session_memories = EmptySessionMemories()
        self.tasks = EmptySearchStore()
        self.task_choice_memories = EmptySearchStore()


class FakeSessions:
    def __init__(self, conversations):
        self._conversations = conversations

    async def conversations_for(self, session_id):
        if session_id != "memory_node:session":
            return []
        return self._conversations


class FakeConversations:
    def __init__(self, messages):
        self._messages = messages

    async def messages_for(self, conversation_id):
        return self._messages.get(conversation_id, [])


class EmptySessionMemories:
    async def for_session(self, _session_id):
        return []


class EmptySearchStore:
    async def search(self):
        return []


def _conversation(node_id, name):
    return _node(node_id, Conversation(name=name))


def _message(node_id, content):
    return _node(node_id, ConversationMessage(role="human", content=content))


def _node(node_id, content):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return MemoryNode(
        id=node_id,
        tags=(),
        timestamps=MemoryTimestamps(
            created_at=now,
            updated_at=now,
            read_at=None,
        ),
        content=content,
    )


if __name__ == "__main__":
    unittest.main()
