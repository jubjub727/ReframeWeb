from __future__ import annotations

from reframe_agent_host.benchmarks.control_flow_case_common import (
    CURRENT_TIMESTAMP,
    available_tasks,
    search_depth_memories,
    session,
    task_choice_memories,
)
from reframe_agent_host.benchmarks.control_flow_case_types import (
    ControlFlowBenchmarkCase,
)
from reframe_agent_host.benchmarks.conversation_evaluation_case_builders import (
    agent,
    conversation,
    human,
    memory,
    thought,
)
from reframe_agent_host.benchmarks.conversation_evaluation_case_tasks import (
    needs_information_task,
)


def stripe_followup_cleanup() -> ControlFlowBenchmarkCase:
    info_task = needs_information_task()
    return ControlFlowBenchmarkCase(
        id="stripe_followup_cleanup",
        current_timestamp=CURRENT_TIMESTAMP,
        current_user_request="Do the same cleanup for the second Stripe CSV.",
        expected_task_id=info_task.id,
        available_tasks=available_tasks(),
        session=session(
            "stripe_csv_cleanup",
            "Stripe CSV cleanup session",
            conversations=(
                conversation(
                    "stripe_csv_cleanup",
                    "Stripe CSV cleanup",
                    (
                        human(
                            "I downloaded January and February CSV exports from "
                            "Stripe. January has duplicate rows after yesterday's "
                            "export hiccup.",
                            "2026-07-03T09:05:00Z",
                        ),
                        thought(
                            "The user named two files conceptually but has not "
                            "provided local paths.",
                            "2026-07-03T09:05:03Z",
                        ),
                        agent(
                            "I can clean January first once you give me the file "
                            "path, then apply the same duplicate-row cleanup to "
                            "February.",
                            "2026-07-03T09:05:06Z",
                        ),
                    ),
                ),
            ),
            memories=(
                memory(
                    "Stripe export pair",
                    "The active cleanup conversation involves January and February "
                    "Stripe CSV exports. January was described as having duplicate "
                    "rows after an export hiccup.",
                    ("stripe", "csv", "spreadsheet"),
                    "2026-07-03T09:05:08Z",
                ),
            ),
        ),
        task_choice_memories=task_choice_memories(),
        conversation_evaluation_memories=(
            memory(
                "Ambiguous second item",
                "Followups such as 'the second one' need the current and recent "
                "conversation objects preserved without guessing file paths.",
                ("followup", "spreadsheet"),
                "2026-07-02T17:00:00Z",
            ),
        ),
        search_depth_memories=search_depth_memories(),
    )
