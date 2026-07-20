import json
import unittest

from baml_sdk import task as baml_task
from baml_sdk import baml as baml_std
from baml_sdk import turn_context as baml_turn_context
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

    async def test_action_history_summary_prompt_is_scoped_to_task_actions(self):
        request = await baml_task.SummariseActionHistory__build_request_async(
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
            "Summarize what the recorded actions for this task attempt did",
            prompt_text,
        )
        self.assertIn("Recorded actions for this task attempt", prompt_text)
        self.assertIn("memory_node:conversation", prompt_text)
        self.assertIn("agent_reply", prompt_text)
        self.assertNotIn("Current conversation", prompt_text)
        self.assertNotIn("Please finish the task.", prompt_text)

    async def test_task_completion_prompt_uses_glm51_pass_fail_gate(self):
        conversation = baml_turn_context.ConversationHistory(
            id="conversation",
            name="Current conversation",
            created_at="created",
            updated_at="updated",
            read_at="read",
            messages=[
                baml_turn_context.ConversationHistoryMessage(
                    created_at="human",
                    updated_at="updated",
                    read_at="read",
                    role="human",
                    content="what is 46 to the power of 3 times 252 plus 5?",
                ),
                baml_turn_context.ConversationHistoryMessage(
                    created_at="validation",
                    updated_at="updated",
                    read_at="read",
                    role="validation_reply",
                    content="Previous retry guidance: check the arithmetic.",
                ),
                baml_turn_context.ConversationHistoryMessage(
                    created_at="agent",
                    updated_at="updated",
                    read_at="read",
                    role="agent",
                    content="24,528,677",
                ),
            ],
        )
        request = await baml_task.CheckTaskCompletion__build_request_async(
            completion_string=(
                "The user received a useful spoken reply that answered or "
                "responded to their message."
            ),
            output_summary="The recorded actions replied to the user.",
            current_conversation=conversation,
        )
        body = json.loads(request.body)
        prompt_text = json.dumps(body["messages"])

        self.assertEqual(body["model"], "glm-5.1")
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertIn("You are a task completion checker.", prompt_text)
        self.assertIn("Completion requirement", prompt_text)
        self.assertIn("Current filtered conversation after task dispatch", prompt_text)
        self.assertIn("Task output summary", prompt_text)
        self.assertIn("Return exactly one token", prompt_text)
        self.assertIn("PASS or FAIL", prompt_text)
        self.assertIn("The user received a useful spoken reply", prompt_text)
        self.assertIn("The recorded actions replied to the user.", prompt_text)
        self.assertIn("persisted conversation role for an agent_reply", prompt_text)
        self.assertIn("24,528,677", prompt_text)
        self.assertIn("validation_reply", prompt_text)
        self.assertIn("Previous retry guidance: check the arithmetic.", prompt_text)
        self.assertIn("Do not require", prompt_text)
        self.assertIn('another \\"fresh\\" reply', prompt_text)
        self.assertIn("Use sound judgment appropriate to the task", prompt_text)
        self.assertIn("Validate the substance", prompt_text)
        self.assertIn("Distinguish material errors", prompt_text)
        self.assertNotIn("numerical answer", prompt_text)
        self.assertNotIn("one-unit difference", prompt_text)
        self.assertNotIn("Small discrepancies", prompt_text)
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
