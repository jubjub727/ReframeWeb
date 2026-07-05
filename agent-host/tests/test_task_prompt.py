import unittest
from datetime import UTC, datetime
from pathlib import Path
import re

from reframe_agent_host.agent_flow.task_prompt import selected_memory_contexts
import baml_sdk as types
from reframe_memory import (
    Conversation,
    ConversationMessage,
    MemoryNode,
    MemoryTimestamps,
    Session,
    SessionMemory,
    Task,
)
from reframe_memory.retrieved_context import (
    RetrievedConversation,
    RetrievedMemoryContext,
    RetrievedPastConversationContext,
    RetrievedSessionContext,
    RetrievedTaskCatalog,
)


class TaskPromptTests(unittest.TestCase):
    def test_task_prompt_model_uses_benchmark_winner(self):
        clients_baml = (
            Path(__file__).resolve().parents[1] / "baml_src" / "clients.baml"
        ).read_text(encoding="utf-8")
        match = re.search(
            r"client<llm>\s+TaskPromptModel\s+\{(?P<body>.*?)\n\}",
            clients_baml,
            flags=re.S,
        )

        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn('model "kimi-k2.6"', body)
        self.assertIn('reasoning_effort "none"', body)

    def test_task_prompt_decision_has_optional_candidate_memory(self):
        decision = types.TaskPromptDecision(
            full_task_prompt="Task:\nAsk only for what matters.\n\nInput:\nAsk for the CSV path.",
            candidate_memory=None,
        )

        self.assertEqual(
            decision.model_dump(mode="json"),
            {
                "full_task_prompt": (
                    "Task:\nAsk only for what matters.\n\nInput:\nAsk for the CSV path."
                ),
                "candidate_memory": None,
            },
        )

    def test_selected_memory_contexts_hide_task_implementation_fields(self):
        contexts = selected_memory_contexts(
            _retrieved_memories(),
            selected_memory_ids=("memory_node:conversation1",),
        )

        rendered = "\n".join(
            f"{context.title}\n{context.description}" for context in contexts
        )
        self.assertIn("Prepare visual panel", rendered)
        self.assertIn("Task description", rendered)
        self.assertIn("Current compact preference", rendered)
        self.assertIn("Past conversation: HN layout conversation", rendered)
        self.assertIn("Please keep Hacker News compact like last time.", rendered)
        self.assertNotIn("Task input", rendered)
        self.assertNotIn("Task output", rendered)
        self.assertNotIn("Task prompt", rendered)
        self.assertNotIn("memory_node:provider", rendered)


def _retrieved_memories():
    task = _task("memory_node:task1", name="Prepare visual panel")
    current_memory = _session_memory(
        "memory_node:currentmemory",
        title="Current compact preference",
    )
    session = _session("memory_node:session1", name="Old Hacker News session")
    conversation = _conversation(
        "memory_node:conversation1",
        name="HN layout conversation",
    )
    message = _message(
        "memory_node:message1",
        content="Please keep Hacker News compact like last time.",
    )
    return RetrievedMemoryContext(
        task_catalog=RetrievedTaskCatalog(tasks=(task,)),
        past_conversation_context=RetrievedPastConversationContext(
            sessions=(
                RetrievedSessionContext(
                    session=session,
                    matched=False,
                    conversations=(
                        RetrievedConversation(
                            conversation=conversation,
                            matched=False,
                            messages=(message,),
                        ),
                    ),
                    session_memories=(),
                ),
            )
        ),
        current_session_memories=(current_memory,),
    )


def _task(node_id, *, name):
    return _node(
        node_id,
        content=Task(
            name=name,
            description="Task description",
            input="Task input",
            output="Task output",
            prompt="Task prompt",
            provider_id="memory_node:provider",
        ),
    )


def _session(node_id, *, name):
    return _node(node_id, content=Session(name=name))


def _conversation(node_id, *, name):
    return _node(node_id, content=Conversation(name=name))


def _message(node_id, *, content):
    return _node(node_id, content=ConversationMessage(role="human", content=content))


def _session_memory(node_id, *, title):
    return _node(
        node_id,
        content=SessionMemory(title=title, description="Memory description"),
    )


def _node(node_id, *, content, tags=()):
    created_at = _dt("2026-02-01T00:00:00Z")
    return MemoryNode(
        id=node_id,
        tags=tuple(tags),
        timestamps=MemoryTimestamps(
            created_at=created_at,
            updated_at=created_at,
            read_at=None,
        ),
        content=content,
    )


def _dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


if __name__ == "__main__":
    unittest.main()
