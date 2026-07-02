from __future__ import annotations

from reframe_agent_host.benchmarks.conversation_evaluation_case_types import (
    ConversationEvaluationBenchmarkCase,
)
from reframe_agent_host.benchmarks.conversation_evaluation_followup_cases import (
    ambiguous_followup,
)
from reframe_agent_host.benchmarks.conversation_evaluation_interaction_cases import (
    scroll_behavior_preference,
)
from reframe_agent_host.benchmarks.conversation_evaluation_preference_cases import (
    remembered_view_preference,
    voice_preference_recall,
)
from reframe_agent_host.benchmarks.conversation_evaluation_safety_cases import (
    capability_limit_with_sensitive_action,
)


def conversation_evaluation_cases() -> tuple[ConversationEvaluationBenchmarkCase, ...]:
    return (
        remembered_view_preference(),
        ambiguous_followup(),
        capability_limit_with_sensitive_action(),
        voice_preference_recall(),
        scroll_behavior_preference(),
    )
