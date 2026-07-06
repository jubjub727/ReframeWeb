import unittest
from datetime import UTC, datetime
from pathlib import Path
import re

from reframe_agent_host.agent_flow.relevance_candidates import filter_retrieved_memories
from reframe_agent_host.agent_flow.task_prompt import (
    build_task_prompt_decision,
    selected_memory_contexts,
)
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
        self.assertIn('model: "kimi-k2.6"', body)
        self.assertIn('reasoning_effort: "none"', body)

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

    def test_task_prompt_decision_stitches_selected_prompt_without_llm_copy(self):
        decision = build_task_prompt_decision(
            selected_task_prompt="Ask only for what matters.",
            composition=types.TaskPromptComposition(
                task_input="Ask for the CSV path.",
                candidate_memory=None,
            ),
        )

        self.assertEqual(
            decision.full_task_prompt,
            "Task:\nAsk only for what matters.\n\nInput:\nAsk for the CSV path.",
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
        self.assertIn("human message", rendered)
        self.assertIn("Please keep Hacker News compact like last time.", rendered)
        self.assertNotIn("Task input", rendered)
        self.assertNotIn("Task output", rendered)
        self.assertNotIn("Task prompt", rendered)
        self.assertNotIn("memory_node:provider", rendered)

    def test_selected_message_contexts_keep_only_relevance_selected_messages(self):
        selected = filter_retrieved_memories(
            _retrieved_memories_with_message_pair(),
            types.RelevantMemoryDecision(
                kept_memory_ids=["memory_node:human1"],
                candidate_memory=None,
            ),
        )
        contexts = selected_memory_contexts(
            selected,
            selected_memory_ids=("memory_node:human1",),
        )

        rendered = "\n".join(
            f"{context.title}\n{context.description}" for context in contexts
        )

        self.assertEqual(
            [context.title for context in contexts],
            [
                "Past session: Past joke session",
                "Past conversation: Joke conversation",
                "human message",
            ],
        )
        self.assertIn("Parent session for selected remembered context.", rendered)
        self.assertIn(
            "Parent conversation for selected remembered context in session: "
            "Past joke session.",
            rendered,
        )
        self.assertIn("human message", rendered)
        self.assertIn("tell me a joke", rendered)
        self.assertNotIn("agent message", rendered)
        self.assertNotIn("library and asks for books about paranoia", rendered)

    def test_selected_session_memory_context_keeps_parent_session_context(self):
        selected = filter_retrieved_memories(
            _retrieved_memories_with_session_memory(),
            types.RelevantMemoryDecision(
                kept_memory_ids=["memory_node:preference1"],
                candidate_memory=None,
            ),
        )
        contexts = selected_memory_contexts(
            selected,
            selected_memory_ids=("memory_node:preference1",),
        )

        rendered = "\n".join(
            f"{context.title}\n{context.description}" for context in contexts
        )

        self.assertEqual(
            [context.title for context in contexts],
            [
                "Past session: Browser preference session",
                "Compact browser rows",
            ],
        )
        self.assertIn("Parent session for selected remembered context.", rendered)
        self.assertIn("Memory description", rendered)

    def test_selected_current_session_context_is_labeled_current(self):
        selected = filter_retrieved_memories(
            _retrieved_memories_with_session_memory(
                session_id="memory_node:current",
                session_name="Current browser session",
            ),
            types.RelevantMemoryDecision(
                kept_memory_ids=["memory_node:preference1"],
                candidate_memory=None,
            ),
        )
        contexts = selected_memory_contexts(
            selected,
            selected_memory_ids=("memory_node:preference1",),
            current_session_id="memory_node:current",
        )

        self.assertEqual(
            [context.title for context in contexts],
            [
                "Current session: Current browser session",
                "Compact browser rows",
            ],
        )


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


def _retrieved_memories_with_message_pair():
    session = _session("memory_node:session2", name="Past joke session")
    conversation = _conversation(
        "memory_node:conversation2",
        name="Joke conversation",
    )
    human = _message(
        "memory_node:human1",
        role="human",
        content="tell me a joke",
    )
    agent = _message(
        "memory_node:agent1",
        role="agent",
        content=(
            "A man walks into a library and asks for books about paranoia. "
            "The librarian whispers that they're right behind him."
        ),
    )
    return RetrievedMemoryContext(
        past_conversation_context=RetrievedPastConversationContext(
            sessions=(
                RetrievedSessionContext(
                    session=session,
                    matched=False,
                    conversations=(
                        RetrievedConversation(
                            conversation=conversation,
                            matched=False,
                            messages=(human, agent),
                            matched_message_ids=(human.id,),
                        ),
                    ),
                    session_memories=(),
                ),
            )
        )
    )


def _retrieved_memories_with_session_memory(
    *,
    session_id="memory_node:session3",
    session_name="Browser preference session",
):
    session = _session(session_id, name=session_name)
    memory = _session_memory(
        "memory_node:preference1",
        title="Compact browser rows",
    )
    return RetrievedMemoryContext(
        past_conversation_context=RetrievedPastConversationContext(
            sessions=(
                RetrievedSessionContext(
                    session=session,
                    matched=False,
                    conversations=(),
                    session_memories=(memory,),
                ),
            )
        )
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


def _message(node_id, *, content, role="human"):
    return _node(node_id, content=ConversationMessage(role=role, content=content))


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
