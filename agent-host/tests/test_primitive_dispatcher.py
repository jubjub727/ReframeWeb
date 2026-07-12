import asyncio
from threading import Event
import unittest
from unittest.mock import patch

from baml_sdk import task_execution as baml_task_execution
from reframe_agent_host.task_execution import PrimitiveDispatcher


class FakeConversations:
    def __init__(self):
        self.messages = []
        self.message_added = Event()

    async def add_message(self, conversation_id, message):
        self.messages.append((conversation_id, message))
        self.message_added.set()


class FakeDatabase:
    def __init__(self):
        self.conversations = FakeConversations()
        self.task_history = FakeTaskHistory()
        self.closed = Event()

    async def close(self):
        self.closed.set()


class FakeTaskHistory:
    def __init__(self):
        self.recorded = []
        self.appended = []

    async def create(self, tags=()):
        return FakeNode("memory_node:task_history")

    async def record_action(self, *, name, input, output, tags=()):
        self.recorded.append(
            {
                "name": name,
                "input": input,
                "output": output,
                "tags": tags,
            }
        )
        return FakeNode(f"memory_node:session_action_{len(self.recorded)}")

    async def append_node(
        self,
        task_history_id,
        *,
        session_id,
        conversation_id,
        actions,
        tags=(),
    ):
        self.appended.append(
            {
                "task_history_id": task_history_id,
                "session_id": session_id,
                "conversation_id": conversation_id,
                "actions": list(actions),
                "tags": tags,
            }
        )
        return FakeNode("memory_node:task_history_node")


class FakeNode:
    def __init__(self, node_id):
        self.id = node_id


class BlockingSpeaker:
    def __init__(self):
        self.started = Event()
        self.release = Event()

    def prepare(self):
        return None

    def speak(self, _text):
        self.started.set()
        self.release.wait(timeout=5)


class EventSpeaker:
    def __init__(self):
        self.finished = Event()

    def prepare(self):
        return None

    def speak(self, text, *, on_event=None):
        if on_event is not None:
            on_event("tts-first-audio", f"text={text}")
        self.finished.set()


class InterruptingSpeaker:
    def __init__(self):
        self.finished = Event()

    def prepare(self):
        return None

    def speak(self, text, *, on_event=None):
        if on_event is not None:
            on_event(
                "tts-interrupted",
                "Last fully spoken word beta at character 10",
            )
        self.finished.set()


class PrimitiveDispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_reply_speech_does_not_block_later_items(self):
        database = FakeDatabase()
        speaker = BlockingSpeaker()
        events = []
        dispatcher = PrimitiveDispatcher(
            database=database,
            conversation_id="conversation:test",
            speaker=speaker,
            on_event=lambda stage, message: events.append((stage, message)),
        )
        result = baml_task_execution.TaskExecutionResult(
            returns=[
                baml_task_execution.TaskReturnItem(
                    name="agent_reply",
                    payload={"text": "spoken reply"},
                ),
                baml_task_execution.TaskReturnItem(
                    name="agent_thought",
                    payload={"text": "next thought"},
                ),
            ]
        )

        try:
            dispatch_result = await asyncio.wait_for(
                dispatcher.dispatch(result),
                timeout=0.5,
            )
        finally:
            speaker.release.set()

        self.assertEqual([record.name for record in dispatch_result.records], [
            "agent_reply",
            "agent_thought",
        ])
        self.assertIn(("agent-reply", "spoken reply"), events)
        self.assertIn(("agent-thought", "next thought"), events)

    async def test_agent_reply_forwards_tts_events(self):
        database = FakeDatabase()
        speaker = EventSpeaker()
        events = []
        dispatcher = PrimitiveDispatcher(
            database=database,
            conversation_id="conversation:test",
            speaker=speaker,
            on_event=lambda stage, message: events.append((stage, message)),
        )

        await dispatcher.dispatch(
            baml_task_execution.TaskExecutionResult(
                returns=[
                    baml_task_execution.TaskReturnItem(
                        name="agent_reply",
                        payload={"text": "spoken reply"},
                    )
                ]
            )
        )

        self.assertTrue(speaker.finished.wait(timeout=1))
        self.assertIn(("tts-first-audio", "text=spoken reply"), events)

    async def test_agent_reply_interruption_is_emitted_and_recorded(self):
        database = FakeDatabase()
        background_database = FakeDatabase()
        speaker = InterruptingSpeaker()
        events = []
        dispatcher = PrimitiveDispatcher(
            database=database,
            conversation_id="conversation:test",
            speaker=speaker,
            on_event=lambda stage, message: events.append((stage, message)),
        )

        async def fake_open_memory_database():
            return background_database

        with patch(
            "reframe_agent_host.task_execution.primitives.open_memory_database",
            fake_open_memory_database,
        ):
            await dispatcher.dispatch(
                baml_task_execution.TaskExecutionResult(
                    returns=[
                        baml_task_execution.TaskReturnItem(
                            name="agent_reply",
                            payload={"text": "spoken reply"},
                        )
                    ]
                )
            )

            self.assertTrue(speaker.finished.wait(timeout=1))
            self.assertTrue(background_database.closed.wait(timeout=1))

        self.assertIn(
            ("agent-reply-interrupted", "Last fully spoken word beta at character 10"),
            events,
        )
        self.assertEqual(
            [
                (conversation_id, message.role, message.content)
                for conversation_id, message in background_database.conversations.messages
            ],
            [
                (
                    "conversation:test",
                    "agent_reply_interrupted",
                    "Last fully spoken word beta at character 10",
                )
            ],
        )

    async def test_conversation_mode_off_invokes_host_callback(self):
        database = FakeDatabase()
        events = []
        mode_changes = []
        dispatcher = PrimitiveDispatcher(
            database=database,
            on_event=lambda stage, message: events.append((stage, message)),
            on_conversation_mode_off=lambda: mode_changes.append("off"),
        )
        result = baml_task_execution.TaskExecutionResult(
            returns=[
                baml_task_execution.TaskReturnItem(
                    name="conversation_mode_off",
                    payload={},
                )
            ]
        )

        dispatch_result = await dispatcher.dispatch(result)

        self.assertEqual(mode_changes, ["off"])
        self.assertEqual(dispatch_result.records[0].name, "conversation_mode_off")
        self.assertEqual(dispatch_result.records[0].status, "ok")
        self.assertIn(
            ("conversation-mode", "continuous conversation off"),
            events,
        )

    async def test_unsupported_action_reply_includes_name_and_payload(self):
        database = FakeDatabase()
        events = []
        dispatcher = PrimitiveDispatcher(
            database=database,
            conversation_id="conversation:test",
            on_event=lambda stage, message: events.append((stage, message)),
        )
        result = baml_task_execution.TaskExecutionResult(
            returns=[
                baml_task_execution.TaskReturnItem(
                    name="website_open",
                    payload={"url": "https://example.com", "reason": "test"},
                )
            ]
        )

        dispatch_result = await dispatcher.dispatch(result)

        detail = dispatch_result.records[0].detail
        self.assertIn("Action not supported: website_open", detail)
        self.assertIn("https://example.com", detail)
        self.assertIn(("agent-reply", detail), events)

    async def test_dispatch_records_task_history_actions(self):
        database = FakeDatabase()
        dispatcher = PrimitiveDispatcher(
            database=database,
            session_id="memory_node:session",
            conversation_id="memory_node:conversation",
        )

        dispatch_result = await dispatcher.dispatch(
            baml_task_execution.TaskExecutionResult(
                returns=[
                    baml_task_execution.TaskReturnItem(
                        name="agent_reply",
                        payload={"text": "done"},
                    ),
                    baml_task_execution.TaskReturnItem(
                        name="conversation_mode_off",
                        payload={},
                    ),
                ]
            )
        )

        self.assertEqual(dispatch_result.task_history_id, "memory_node:task_history")
        self.assertEqual(
            dispatch_result.task_history_node_id,
            "memory_node:task_history_node",
        )
        self.assertEqual(
            [record["name"] for record in database.task_history.recorded],
            ["agent_reply", "conversation_mode_off"],
        )
        self.assertEqual(
            database.task_history.recorded[0]["input"],
            {"text": "done"},
        )
        self.assertEqual(
            database.task_history.recorded[0]["output"]["text"],
            "done",
        )
        self.assertEqual(
            database.task_history.appended[0],
            {
                "task_history_id": "memory_node:task_history",
                "session_id": "memory_node:session",
                "conversation_id": "memory_node:conversation",
                "actions": [
                    "memory_node:session_action_1",
                    "memory_node:session_action_2",
                ],
                "tags": ("task-execution",),
            },
        )


if __name__ == "__main__":
    unittest.main()
