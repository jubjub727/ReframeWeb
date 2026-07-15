import json
import unittest
from datetime import UTC, datetime

from baml_sdk import turn_context as baml_turn_context
from baml_sdk import task_catalog as baml_task_catalog
from baml_sdk import task as baml_task
from reframe_agent_host.agent_flow.machine_state import local_machine_state_context
from reframe_agent_host.agent_flow.task_choice import TaskChoiceContextBuilder
from reframe_agent_host.commands.parser import build_parser
from reframe_memory import (
    Conversation,
    ConversationMessage,
    MemoryNode,
    MemoryTimestamps,
    UserPreferenceMemory,
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

    async def test_context_includes_user_preferences(self):
        context = await TaskChoiceContextBuilder(
            database=FakeDatabase(),
            session_id="memory_node:session",
        ).build()

        self.assertEqual(len(context.user_preferences), 1)
        self.assertEqual(context.user_preferences[0].title, "Interface density")
        self.assertIn("compact", context.user_preferences[0].tags)

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

    async def test_choose_task_prompt_renders_user_preferences(self):
        request = await baml_task.ChooseTask__build_request_async(
            current_user_request="Open Hacker News compactly.",
            current_conversation=None,
            session_memories=[],
            user_preferences=[
                baml_turn_context.UserPreferenceMemoryContext(
                    id="memory_node:pref1",
                    title="Interface density",
                    description="Prefer compact, information-dense interfaces.",
                    tags=["compact", "ui"],
                    created_at="2026-01-01T00:00:00Z",
                    updated_at="2026-01-01T00:00:00Z",
                    read_at="NONE",
                )
            ],
            available_tasks=[
                baml_task_catalog.AvailableTask(
                    id="task:visual_panel",
                    name="Visual panel",
                    description="Open a visual panel.",
                    input="The user's request.",
                    output="A rendered panel.",
                    prompt="Use the store and panel.",
                    provider_id="provider:test",
                    model_id="glm-5.1",
                    created_at="2026-01-01T00:00:00Z",
                    updated_at="2026-01-01T00:00:00Z",
                    read_at="NONE",
                )
            ],
            task_choice_memories=[],
            machine_state=local_machine_state_context("test"),
        )

        body = json.loads(request.body)
        rendered = json.dumps(body)

        self.assertIn("User preferences:", rendered)
        self.assertIn("Interface density", rendered)
        self.assertIn("Prefer compact, information-dense interfaces.", rendered)


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
        self.user_preferences = SearchStore([_user_preference("memory_node:pref1")])
        self.tasks = SearchStore([])
        self.task_choice_memories = SearchStore([])


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


class SearchStore:
    def __init__(self, items):
        self._items = items

    async def search(self):
        return self._items


def _conversation(node_id, name):
    return _node(node_id, Conversation(name=name))


def _message(node_id, content):
    return _node(node_id, ConversationMessage(role="human", content=content))


def _user_preference(node_id):
    return _node(
        node_id,
        UserPreferenceMemory(
            title="Interface density",
            description="Prefer compact, information-dense interfaces.",
        ),
        tags=("compact", "ui"),
    )


def _node(node_id, content, tags=()):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return MemoryNode(
        id=node_id,
        tags=tags,
        timestamps=MemoryTimestamps(
            created_at=now,
            updated_at=now,
            read_at=None,
        ),
        content=content,
    )


if __name__ == "__main__":
    unittest.main()
