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


if __name__ == "__main__":
    unittest.main()
