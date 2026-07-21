import json
import unittest

from baml_sdk import task as baml_task
from baml_sdk import baml as baml_std
from baml_sdk import turn_context as baml_turn_context
from baml_sdk import voice_turn as baml_voice_turn
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
        prompt_text = json.dumps(body["messages"]).replace("\\n", " ")

        self.assertIn(
            "Summarize what the recorded actions for this task attempt did",
            prompt_text,
        )
        self.assertIn("Recorded actions for this task attempt", prompt_text)
        self.assertIn("Preserve payload values exactly", prompt_text)
        self.assertIn("without speculating about the request", prompt_text)
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
            current_user_request="what is 46 to the power of 3 times 252 plus 5?",
            completion_string=(
                "The user received a useful spoken reply that answered or "
                "responded to their message."
            ),
            output_summary="The recorded actions replied to the user.",
            current_conversation=conversation,
        )
        body = json.loads(request.body)
        prompt_text = json.dumps(body["messages"]).replace("\\n", " ")
        system_prompt = json.dumps(body["messages"][0]).replace("\\n", " ")

        self.assertEqual(body["model"], "glm-5.1")
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertIn("fast, conservative completion validator", prompt_text)
        self.assertIn("active user request defines what matters", prompt_text)
        self.assertIn("Start at PASS and make one short validation pass", prompt_text)
        self.assertIn("compact failure evidence", prompt_text)
        self.assertIn("candidate-centered check", prompt_text)
        self.assertIn("candidate-sized value", prompt_text)
        self.assertIn("Test stated constraints or transformations", prompt_text)
        self.assertIn("Never redo the original task", prompt_text)
        self.assertIn("Completion requirement", prompt_text)
        self.assertIn("Active user request", prompt_text)
        self.assertIn("Task output summary", prompt_text)
        self.assertIn("PASS or FAIL", prompt_text)
        self.assertIn("The user received a useful spoken reply", prompt_text)
        self.assertIn("The recorded actions replied to the user.", prompt_text)
        self.assertIn("Conversation history for delivery and background", prompt_text)
        self.assertIn("delivery structures as envelopes around outcomes", prompt_text)
        self.assertIn("agent, agent_reply, or agent_message", prompt_text)
        self.assertIn("delivered reply is the text payload alone", prompt_text)
        self.assertIn("transport metadata", prompt_text)
        self.assertIn("not visible prefixes, suffixes, framing", prompt_text)
        self.assertIn("Apply content and presentation requirements only", prompt_text)
        self.assertIn("24,528,677", prompt_text)
        self.assertIn("validation_reply", prompt_text)
        self.assertIn("Previous retry guidance: check the arithmetic.", prompt_text)
        self.assertIn("not an answer key", prompt_text)
        self.assertIn("proposed answers and validation claims do not establish", prompt_text)
        self.assertIn("ordinary, open-ended", prompt_text)
        self.assertIn("false FAIL is worse", prompt_text)
        self.assertIn("smallest concrete mismatch", prompt_text)
        self.assertNotIn("numerical answer", prompt_text)
        self.assertNotIn("arithmetic", system_prompt.lower())
        self.assertNotIn("equation", system_prompt.lower())
        self.assertNotIn("exponent", system_prompt.lower())
        self.assertNotIn("power of", system_prompt.lower())
        self.assertNotIn("one-unit difference", prompt_text)
        self.assertNotIn("Small discrepancies", prompt_text)
        self.assertNotIn("reference executor", prompt_text)
        self.assertNotIn("second construction", prompt_text)
        self.assertNotIn("Check the resulting reference backwards", prompt_text)
        self.assertNotIn("unverified", prompt_text.lower())
        self.assertNotIn("cannot be established", prompt_text.lower())
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
        prompt_text = json.dumps(body["messages"]).replace("\\n", " ")

        self.assertEqual(body["model"], "glm-5.1")
        self.assertIn("unsuccessful task attempt", prompt_text)
        self.assertIn("validation_reply", prompt_text)
        self.assertIn("can_refine", prompt_text)
        self.assertIn("Earlier refusal replies from this task session", prompt_text)
        self.assertIn("Include the missing answer", prompt_text)
        self.assertIn("concise validation guidance", prompt_text)
        self.assertIn("A terse result", prompt_text)
        self.assertIn("does not add unstated wording", prompt_text)
        self.assertIn("most direct substantive mismatch", prompt_text)
        self.assertIn("Recorded delivery structures are envelopes", prompt_text)
        self.assertIn("treat that payload alone as the delivered reply", prompt_text)
        self.assertIn("as added framing or as a presentation defect", prompt_text)
        self.assertIn("supported reason the result failed", prompt_text)
        self.assertIn("useful specificity", prompt_text)
        self.assertIn("what should be checked or", prompt_text)
        self.assertIn("bare rejection", prompt_text)
        self.assertIn("generic instruction to try again", prompt_text)
        self.assertIn("more reliable task-appropriate approach", prompt_text)
        self.assertIn("easier to audit", prompt_text)
        self.assertIn("Merely asking it to check again", prompt_text)
        self.assertIn("only the concrete failure", prompt_text)
        self.assertIn("optional improvements", prompt_text)
        self.assertIn("Perform any analysis needed", prompt_text)
        self.assertIn("correct or expected outcome and its derivation internal", prompt_text)
        self.assertIn("replacement result, exact corrected content", prompt_text)
        self.assertIn("intermediate work, a worked solution", prompt_text)
        self.assertIn("Return guidance, not a solution", prompt_text)
        self.assertIn("partial answer", prompt_text)
        self.assertIn("identifying check value", prompt_text)
        self.assertIn("copyable example", prompt_text)
        self.assertIn("do not introduce illustrative answer content", prompt_text)
        self.assertNotIn("The user received a useful reply.", prompt_text)
        self.assertNotIn("reconsider", prompt_text.lower())
        self.assertNotIn("do not mention", prompt_text.lower())
        self.assertNotIn("bool or null", prompt_text)

    async def test_request_completion_checks_coverage_without_revalidating_tasks(self):
        request = await baml_voice_turn.CheckRequestCompletion__build_request_async(
            current_user_request="Answer the calculation.",
            current_conversation=None,
            successful_tasks=[
                baml_voice_turn.SuccessfulVoiceTaskResult(
                    task_name="Reply to user",
                    completion_requirement="The user received a useful reply.",
                    output_summary="The reply was posted.",
                )
            ],
        )
        body = json.loads(request.body)
        prompt_text = json.dumps(body["messages"])

        self.assertIn("request-coverage check", prompt_text)
        self.assertIn("Treat those confirmations as authoritative", prompt_text)
        self.assertIn("not re-check their correctness", prompt_text)
        self.assertIn("another distinct task is still needed", prompt_text)
        self.assertNotIn("accurate and appropriate response", prompt_text)


if __name__ == "__main__":
    unittest.main()
