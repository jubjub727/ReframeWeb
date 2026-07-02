from __future__ import annotations

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
from reframe_agent_host.benchmarks.conversation_evaluation_case_types import (
    ConversationEvaluationBenchmarkCase,
)


def ambiguous_followup() -> ConversationEvaluationBenchmarkCase:
    return ConversationEvaluationBenchmarkCase(
        id="ambiguous_followup",
        current_user_request="Do the same thing for the second one.",
        selected_task=needs_information_task(),
        session_conversations=(
            conversation(
                "ambiguous_followup",
                "Spreadsheet cleanup discussion",
                (
                    human(
                        "I downloaded the January and February CSV exports from "
                        "Stripe. January has duplicate rows after yesterday's "
                        "export hiccup.",
                        "2026-07-02T11:15:00Z",
                    ),
                    thought(
                        "The user has named two Stripe CSV exports and one "
                        "operation, but has not provided any local file paths.",
                        "2026-07-02T11:15:03Z",
                    ),
                    agent(
                        "I can clean January first once you give me the file "
                        "path, then apply the same duplicate-row cleanup to "
                        "February.",
                        "2026-07-02T11:15:06Z",
                    ),
                    human(
                        "Do the same thing for the second one.",
                        "2026-07-02T11:17:00Z",
                    ),
                    thought(
                        "Task choice selected request-more-information; the "
                        "second item is February, but the file path is still "
                        "missing.",
                        "2026-07-02T11:17:02Z",
                    ),
                ),
            ),
        ),
        session_memories=(
            memory(
                "Stripe export pair",
                "The active cleanup conversation involves two Stripe CSV "
                "exports named January and February. January was described as "
                "having duplicate rows after an export hiccup.",
                ("stripe", "csv", "spreadsheet"),
                "2026-07-02T11:15:08Z",
            ),
        ),
        conversation_evaluation_memories=(),
        review_focus="Review whether hints preserve the CSV/Stripe context without guessing a file path.",
    )
