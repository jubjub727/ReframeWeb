from types import SimpleNamespace
import unittest

import baml_sdk as types
from reframe_agent_host.commands.memory_output import (
    memory_search_summary,
    memory_type_counts_summary,
    search_depth_summary,
    selected_memory_type_counts_summary,
)


class MemoryOutputTests(unittest.TestCase):
    def test_memory_search_summary_lists_tags_and_string_terms(self):
        hints = types.ConversationMemorySearchHints(
            tags=types.MemoryTagSearch(
                any_of=["voice", "latency"],
                all_of=["agent-host"],
                none_of=["scratch"],
            ),
            strings=types.MemoryStringSearch(
                contains=["sub second"],
                equals=["exact title"],
            ),
            candidate_memory=None,
        )

        self.assertEqual(
            memory_search_summary(hints),
            (
                'tags_any=["voice", "latency"] '
                'tags_all=["agent-host"] '
                'tags_none=["scratch"] '
                'strings_contains=["sub second"] '
                'strings_equals=["exact title"]'
            ),
        )

    def test_search_depth_summary_lists_domains_and_cutoffs(self):
        depths = types.SearchDepthDecision(
            depths={
                "task_catalog": types.SearchDepthTimestamps(
                    created_after="2026-01-01T00:00:00Z",
                    updated_after="2026-01-02T00:00:00Z",
                    read_after="2026-01-03T00:00:00Z",
                ),
                "past_conversation_context": types.SearchDepthTimestamps(
                    created_after="2026-02-01T00:00:00Z",
                    updated_after="2026-02-02T00:00:00Z",
                    read_after="2026-02-03T00:00:00Z",
                ),
            },
            candidate_memory=None,
        )

        self.assertEqual(
            search_depth_summary(depths),
            (
                "domains=[task_catalog("
                "created_after=2026-01-01T00:00:00Z, "
                "updated_after=2026-01-02T00:00:00Z, "
                "read_after=2026-01-03T00:00:00Z); "
                "past_conversation_context("
                "created_after=2026-02-01T00:00:00Z, "
                "updated_after=2026-02-02T00:00:00Z, "
                "read_after=2026-02-03T00:00:00Z)]"
            ),
        )

    def test_memory_type_counts_summary_uses_candidate_kinds(self):
        memories = SimpleNamespace(
            task_catalog=SimpleNamespace(tasks=(object(), object())),
            current_session_memories=(object(),),
            past_conversation_context=SimpleNamespace(
                sessions=(
                    SimpleNamespace(
                        session=object(),
                        conversations=(
                            SimpleNamespace(
                                conversation=object(),
                                messages=(object(), object(), object()),
                            ),
                        ),
                        session_memories=(object(), object()),
                    ),
                    SimpleNamespace(
                        session=object(),
                        conversations=(),
                        session_memories=(),
                    ),
                )
            ),
        )

        self.assertEqual(
            memory_type_counts_summary(memories),
            (
                "total=11 task=2 current_session_memory=1 "
                "past_session=2 past_session_memory=2 "
                "past_conversation=1 past_conversation_message=3"
            ),
        )

    def test_memory_type_counts_summary_can_separate_current_session(self):
        memories = SimpleNamespace(
            task_catalog=SimpleNamespace(tasks=()),
            current_session_memories=(_node("current-memory-1"),),
            past_conversation_context=SimpleNamespace(
                sessions=(
                    SimpleNamespace(
                        session=_node("current-session"),
                        conversations=(
                            SimpleNamespace(
                                conversation=_node("current-conversation"),
                                messages=(_node("current-message"),),
                            ),
                        ),
                        session_memories=(),
                    ),
                    SimpleNamespace(
                        session=_node("past-session"),
                        conversations=(
                            SimpleNamespace(
                                conversation=_node("past-conversation"),
                                messages=(_node("past-message"),),
                            ),
                        ),
                        session_memories=(_node("past-memory"),),
                    ),
                )
            ),
        )

        self.assertEqual(
            memory_type_counts_summary(memories, "current-session"),
            (
                "total=8 task=0 current_session=1 current_session_memory=1 "
                "current_conversation=1 current_conversation_message=1 "
                "past_session=1 past_session_memory=1 past_conversation=1 "
                "past_conversation_message=1"
            ),
        )

    def test_selected_memory_type_counts_summary_uses_kept_ids(self):
        memories = SimpleNamespace(
            task_catalog=SimpleNamespace(tasks=(_node("task-1"),)),
            current_session_memories=(_node("current-memory-1"),),
            past_conversation_context=SimpleNamespace(
                sessions=(
                    SimpleNamespace(
                        session=_node("session-1"),
                        conversations=(
                            SimpleNamespace(
                                conversation=_node("conversation-1"),
                                messages=(_node("message-1"), _node("message-2")),
                            ),
                        ),
                        session_memories=(_node("session-memory-1"),),
                    ),
                )
            ),
        )

        self.assertEqual(
            selected_memory_type_counts_summary(
                memories,
                ("message-2", "conversation-1", "missing-id"),
            ),
            (
                "total=3 task=0 current_session_memory=0 "
                "past_session=0 past_session_memory=0 "
                "past_conversation=1 past_conversation_message=1 unknown=1"
            ),
        )

def _node(node_id):
    return SimpleNamespace(id=node_id)


if __name__ == "__main__":
    unittest.main()
