from __future__ import annotations

from reframe_agent_host.benchmarks.control_flow_case_types import (
    ControlFlowBenchmarkCase,
)
from reframe_agent_host.benchmarks.control_flow_followup_cases import (
    stripe_followup_cleanup,
)
from reframe_agent_host.benchmarks.control_flow_visual_cases import (
    hacker_news_compact_panel,
    reddit_slow_scroll,
)


def control_flow_cases() -> tuple[ControlFlowBenchmarkCase, ...]:
    return (
        hacker_news_compact_panel(),
        reddit_slow_scroll(),
        stripe_followup_cleanup(),
    )
