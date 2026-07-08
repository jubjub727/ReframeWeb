import unittest
from dataclasses import MISSING, fields

from reframe_agent_host.magic_providers import MAGIC_DO_NOTHING_MODEL_ID
from reframe_agent_host.memory_seed import core_task_definitions
from reframe_agent_host.memory_seed.core_task_definitions import (
    CORE_TASKS,
    CoreTaskDefinition,
)


class CoreTaskDefinitionTests(unittest.TestCase):
    def test_core_tasks_do_not_use_shared_prompt_fragments_or_tags(self):
        self.assertFalse(hasattr(core_task_definitions, "CORE_TASK_RETURN_OPTIONS"))
        self.assertFalse(hasattr(core_task_definitions, "CORE_TASK_TAGS"))
        self.assertFalse(hasattr(core_task_definitions, "CORE_TASK_MODEL_ID"))
        self.assertFalse(hasattr(core_task_definitions, "CORE_TASK_REASONING_EFFORT"))

    def test_core_task_inputs_describe_user_supplied_text_only(self):
        inputs = {task.name: task.input for task in CORE_TASKS}

        self.assertEqual(
            inputs["Explain request cannot be handled"],
            "The user's request.",
        )
        self.assertEqual(
            inputs["Request more information from the user"],
            "The user's request.",
        )
        self.assertEqual(
            inputs["Turn conversation mode off"],
            "The user's request to end continuous conversation.",
        )
        self.assertEqual(
            inputs["Thinking"],
            "The user's request or conversational context.",
        )
        self.assertEqual(
            inputs["Do nothing"],
            "The user's request or conversational context.",
        )
        self.assertEqual(
            inputs["Greeting"],
            "The user's greeting or conversational opener.",
        )
        self.assertEqual(inputs["Reply to user"], "The user's message.")

    def test_new_core_tasks_have_task_owned_return_items(self):
        tasks = {task.name: task for task in CORE_TASKS}

        self.assertIn("Turn conversation mode off", tasks)
        self.assertIn("Thinking", tasks)
        self.assertIn("Do nothing", tasks)
        self.assertIn("Greeting", tasks)
        self.assertIn("Reply to user", tasks)
        self.assertIn(
            "conversation_mode_off with empty payload {}",
            tasks["Turn conversation mode off"].prompt,
        )
        self.assertIn(
            'agent_reply with payload {"text": "..."}',
            tasks["Reply to user"].prompt,
        )
        self.assertIn(
            "Do not return agent_reply just to acknowledge",
            tasks["Reply to user"].prompt,
        )
        self.assertIn("empty returns array", tasks["Reply to user"].prompt)
        self.assertIn(
            "Only reply when it's appropriate.",
            tasks["Reply to user"].prompt,
        )
        self.assertIn(
            'agent_thought with payload {"text": "..."}',
            tasks["Thinking"].prompt,
        )
        self.assertIn(
            'session_memory with payload {"title": "...", "description": "..."}',
            tasks["Thinking"].prompt,
        )
        self.assertIn(
            'user_preference with payload {"title": "...", "description": "..."}',
            tasks["Thinking"].prompt,
        )
        self.assertNotIn(
            'agent_reply with payload {"text": "..."}',
            tasks["Thinking"].prompt,
        )
        self.assertIn("empty returns array", tasks["Thinking"].prompt)
        self.assertEqual(
            tasks["Explain request cannot be handled"].output,
            "The user received a clear explanation that the request cannot be "
            "handled, including the relevant limitation or boundary and a "
            "useful next step when available.",
        )
        self.assertEqual(
            tasks["Request more information from the user"].output,
            "The user was asked for the specific missing information needed "
            "to continue the task.",
        )
        self.assertEqual(
            tasks["Turn conversation mode off"].output,
            "Continuous conversation mode was turned off.",
        )
        self.assertEqual(
            tasks["Thinking"].output,
            "Useful non-spoken context was preserved as an internal thought, "
            "session memory, or user preference.",
        )
        self.assertEqual(tasks["Do nothing"].output, "")
        self.assertIn("Return an empty returns array", tasks["Do nothing"].prompt)
        self.assertIn(
            'agent_reply with payload {"text": "..."}',
            tasks["Greeting"].prompt,
        )
        self.assertEqual(
            tasks["Greeting"].output,
            "The user received a brief, natural greeting or conversational "
            "acknowledgement.",
        )
        self.assertEqual(
            tasks["Reply to user"].output,
            "The user received a useful spoken reply that answered or "
            "responded to their message.",
        )
        self.assertNotIn(
            'agent_thought with payload {"text": "..."}',
            tasks["Greeting"].prompt,
        )
        self.assertNotIn(
            'session_memory with payload {"title": "...", "description": "..."}',
            tasks["Greeting"].prompt,
        )
        self.assertNotIn(
            'user_preference with payload {"title": "...", "description": "..."}',
            tasks["Greeting"].prompt,
        )
        self.assertIn("Use only the item type listed above.", tasks["Greeting"].prompt)
        self.assertIn("brief, warm, and style-matched", tasks["Greeting"].prompt)
        self.assertEqual(
            tasks["Turn conversation mode off"].tags,
            ("conversation-mode", "conversation-off"),
        )
        self.assertEqual(
            tasks["Turn conversation mode off"].model_id,
            "kimi-k2.6",
        )
        self.assertEqual(
            tasks["Turn conversation mode off"].reasoning_effort,
            "none",
        )
        self.assertEqual(tasks["Thinking"].tags, ("thinking", "silent", "memory"))
        self.assertEqual(tasks["Thinking"].model_id, "glm-5.1")
        self.assertEqual(tasks["Thinking"].reasoning_effort, "none")
        self.assertEqual(tasks["Do nothing"].tags, ("nothing", "silent"))
        self.assertEqual(tasks["Do nothing"].model_id, MAGIC_DO_NOTHING_MODEL_ID)
        self.assertIsNone(tasks["Do nothing"].reasoning_effort)
        self.assertEqual(tasks["Greeting"].tags, ("greeting", "reply"))
        self.assertEqual(tasks["Greeting"].model_id, "glm-5.1")
        self.assertEqual(tasks["Greeting"].reasoning_effort, "none")
        self.assertEqual(tasks["Reply to user"].tags, ("reply",))
        self.assertEqual(tasks["Reply to user"].model_id, "glm-5.1")
        self.assertEqual(tasks["Reply to user"].reasoning_effort, "none")

    def test_every_core_task_declares_its_provider_choice(self):
        expected = {
            "Explain request cannot be handled": ("glm-5.1", "none"),
            "Request more information from the user": ("glm-5.1", "none"),
            "Turn conversation mode off": ("kimi-k2.6", "none"),
            "Thinking": ("glm-5.1", "none"),
            "Do nothing": (MAGIC_DO_NOTHING_MODEL_ID, None),
            "Greeting": ("glm-5.1", "none"),
            "Reply to user": ("glm-5.1", "none"),
        }
        for task in CORE_TASKS:
            with self.subTest(task=task.name):
                self.assertIsInstance(task.model_id, str)
                self.assertTrue(task.model_id)
                if task.reasoning_effort is not None:
                    self.assertIsInstance(task.reasoning_effort, str)
                    self.assertTrue(task.reasoning_effort)
                self.assertEqual(
                    (task.model_id, task.reasoning_effort),
                    expected[task.name],
                )

        field_defaults = {field.name: field.default for field in fields(CoreTaskDefinition)}
        self.assertIs(field_defaults["model_id"], MISSING)
        self.assertIs(field_defaults["reasoning_effort"], MISSING)


if __name__ == "__main__":
    unittest.main()
