import asyncio
from threading import Event
import unittest

import baml_sdk as types
from reframe_agent_host.task_execution import PrimitiveDispatcher


class FakeConversations:
    def __init__(self):
        self.messages = []

    async def add_message(self, conversation_id, message):
        self.messages.append((conversation_id, message))


class FakeDatabase:
    def __init__(self):
        self.conversations = FakeConversations()


class BlockingSpeaker:
    def __init__(self):
        self.started = Event()
        self.release = Event()

    def prepare(self):
        return None

    def speak(self, _text):
        self.started.set()
        self.release.wait(timeout=5)


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
        result = types.TaskExecutionResult(
            returns=[
                types.TaskReturnItem(
                    name="agent_reply",
                    payload={"text": "spoken reply"},
                ),
                types.TaskReturnItem(
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

    async def test_conversation_mode_off_invokes_host_callback(self):
        database = FakeDatabase()
        events = []
        mode_changes = []
        dispatcher = PrimitiveDispatcher(
            database=database,
            on_event=lambda stage, message: events.append((stage, message)),
            on_conversation_mode_off=lambda: mode_changes.append("off"),
        )
        result = types.TaskExecutionResult(
            returns=[
                types.TaskReturnItem(
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
        result = types.TaskExecutionResult(
            returns=[
                types.TaskReturnItem(
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


if __name__ == "__main__":
    unittest.main()
