import unittest

from baml_sdk import turn_context as baml_turn_context
from reframe_agent_host.voice.conversation_mode import ConversationModeController


class ConversationModeControllerTests(unittest.TestCase):
    def test_turn_off_conversation_returns_to_wake_command_mode(self):
        controller = ConversationModeController(
            baml_turn_context.ConversationMode.CONTINUOUS_CONVERSATION
        )

        changed = controller.turn_off_conversation()

        self.assertTrue(changed)
        self.assertEqual(controller.get(), baml_turn_context.ConversationMode.WAKE_COMMAND)

    def test_setting_existing_mode_does_not_advance_version(self):
        controller = ConversationModeController(baml_turn_context.ConversationMode.WAKE_COMMAND)
        _mode, version = controller.snapshot()

        changed = controller.turn_off_conversation()

        self.assertFalse(changed)
        self.assertEqual(controller.snapshot()[1], version)


if __name__ == "__main__":
    unittest.main()
