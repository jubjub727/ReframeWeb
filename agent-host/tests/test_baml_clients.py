import json
import unittest

import baml_sdk as baml
from baml_sdk import baml as baml_std
from reframe_agent_host.agent_flow.baml_clients import (
    client_kwargs,
    compiled_client,
)


class BamlClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_compiled_client_uses_sdk_client_type(self):
        client = compiled_client("OpenCodeGoModelDeepseekV4FlashReasoningHigh")

        self.assertIsInstance(client, baml_std.llm.Client)
        self.assertEqual(client.client_type, baml_std.llm.ClientType.Primitive)

        request = await baml.PerformTask__build_request_async(
            full_task_prompt="Task:\nReturn no response items.",
            **client_kwargs(client),
        )
        body = json.loads(request.body)

        self.assertEqual(body["model"], "deepseek-v4-flash")
        self.assertEqual(body["reasoning_effort"], "high")

    async def test_action_history_summary_prompt_uses_history_and_conversation(self):
        request = await baml.SummariseActionHistory__build_request_async(
            current_conversation=None,
            recorded_action_history=(
                "- Session: memory_node:session\n"
                "  Conversation: memory_node:conversation\n"
                "  Actions:\n"
                "  - Action:\n"
                "      name: agent_reply\n"
                "      input:\n"
                '        {"text": "done"}\n'
                "      output:\n"
                '        {"text": "done"}'
            ),
            **client_kwargs("OpenCodeGoModelDeepseekV4FlashReasoningHigh"),
        )
        body = json.loads(request.body)
        prompt_text = json.dumps(body["messages"])

        self.assertIn(
            "Given the current conversation and the recorded action history",
            prompt_text,
        )
        self.assertIn("Recorded action history", prompt_text)
        self.assertIn("agent_reply", prompt_text)
        self.assertNotIn("Current task", prompt_text)


if __name__ == "__main__":
    unittest.main()
