import json
import unittest

from baml_sdk import task as baml_task
from baml_sdk import turn_context as baml_turn_context
from baml_sdk import baml as baml_std
from reframe_agent_host.agent_flow.provider_clients import (
    client_kwargs,
    compiled_client,
)


class ProviderClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_compiled_client_uses_sdk_client_type(self):
        client = compiled_client("opencode_go.OpenCodeGoModelDeepseekV4FlashReasoningHigh")

        self.assertIsInstance(client, baml_std.llm.Client)
        self.assertEqual(client.client_type, baml_std.llm.ClientType.Primitive)

        request = await baml_task.PerformTask__build_request_async(
            full_task_prompt="Task:\nReturn no response items.",
            **client_kwargs(client),
        )
        body = json.loads(request.body)

        self.assertEqual(body["model"], "deepseek-v4-flash")
        self.assertEqual(body["reasoning_effort"], "high")

    async def test_action_history_summary_prompt_uses_history_and_conversation(self):
        request = await baml_task.SummariseActionHistory__build_request_async(
            current_conversation=baml_turn_context.ConversationHistory(
                id="memory_node:conversation",
                name="Current conversation",
                created_at="2026-07-13T00:00:00Z",
                updated_at="2026-07-13T00:01:00Z",
                read_at="NONE",
                messages=[
                    baml_turn_context.ConversationHistoryMessage(
                        created_at="2026-07-13T00:00:00Z",
                        updated_at="2026-07-13T00:00:00Z",
                        read_at="NONE",
                        role="user",
                        content="Please finish the task.",
                    )
                ],
            ),
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
            **client_kwargs("opencode_go.OpenCodeGoModelDeepseekV4FlashReasoningHigh"),
        )
        body = json.loads(request.body)
        prompt_text = json.dumps(body["messages"])

        self.assertIn(
            "Given the current conversation and the recorded action history",
            prompt_text,
        )
        self.assertIn("Recorded action history", prompt_text)
        self.assertIn("memory_node:conversation", prompt_text)
        self.assertIn("Please finish the task.", prompt_text)
        self.assertIn("agent_reply", prompt_text)
        self.assertNotIn("Current task", prompt_text)

    async def test_task_completion_prompt_uses_glm51_pass_fail_gate(self):
        request = await baml_task.CheckTaskCompletion__build_request_async(
            completion_string=(
                "The user received a useful spoken reply that answered or "
                "responded to their message."
            ),
            output_summary="The recorded actions replied to the user.",
        )
        body = json.loads(request.body)
        prompt_text = json.dumps(body["messages"])

        self.assertEqual(body["model"], "glm-5.1")
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertIn("You are a task completion checker.", prompt_text)
        self.assertIn("Completion requirement", prompt_text)
        self.assertIn("Task output summary", prompt_text)
        self.assertIn("Return exactly one token", prompt_text)
        self.assertIn("PASS or FAIL", prompt_text)
        self.assertIn("The user received a useful spoken reply", prompt_text)
        self.assertIn("The recorded actions replied to the user.", prompt_text)
        self.assertNotIn("{{ completion_string }}", prompt_text)
        self.assertNotIn("{{ output_summary }}", prompt_text)
        self.assertNotIn("{{ ctx.output_format }}", prompt_text)
        self.assertNotIn("confidence", prompt_text.lower())
        self.assertNotIn("too vague", prompt_text.lower())

    async def test_failure_reply_prompt_runs_after_existing_fail_gate(self):
        request = await baml_task.WriteValidationReply__build_request_async(
            task_prompt="Task:\nReply usefully.\n\nInput:\nPlease help.",
            completion_string="The user received a useful reply.",
            output_summary="The recorded actions did not answer the request.",
            earlier_refusal_reply_text="- Include the missing answer.",
        )
        body = json.loads(request.body)
        prompt_text = json.dumps(body["messages"])

        self.assertEqual(body["model"], "glm-5.1")
        self.assertIn("unsuccessful task attempt", prompt_text)
        self.assertIn("validation_reply", prompt_text)
        self.assertIn("can_refine", prompt_text)
        self.assertIn("Earlier refusal replies from this task session", prompt_text)
        self.assertIn("Include the missing answer", prompt_text)
        self.assertNotIn("reconsider", prompt_text.lower())
        self.assertNotIn("do not mention", prompt_text.lower())
        self.assertNotIn("bool or null", prompt_text)


if __name__ == "__main__":
    unittest.main()
