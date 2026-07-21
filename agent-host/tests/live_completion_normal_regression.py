from __future__ import annotations

import argparse
import asyncio
import time

from baml_sdk import task as baml_task
from baml_sdk import turn_context as baml_turn_context

from reframe_agent_host.agent_flow.provider_clients import client_kwargs

from tests.completion_normal_cases import NORMAL_COMPLETION_CASES


def _conversation(request: str, candidate: str):
    return baml_turn_context.ConversationHistory(
        id="normal-validation",
        name="Normal validation",
        created_at="2026-07-21T00:00:00Z",
        updated_at="2026-07-21T00:00:02Z",
        read_at="2026-07-21T00:00:02Z",
        messages=[
            baml_turn_context.ConversationHistoryMessage(
                created_at="2026-07-21T00:00:00Z",
                updated_at="2026-07-21T00:00:00Z",
                read_at="2026-07-21T00:00:00Z",
                role="human",
                content=request,
            ),
            baml_turn_context.ConversationHistoryMessage(
                created_at="2026-07-21T00:00:01Z",
                updated_at="2026-07-21T00:00:01Z",
                read_at="2026-07-21T00:00:01Z",
                role="agent",
                content=candidate,
            ),
        ],
    )


async def _run(cases: tuple[tuple[str, str], ...], client_name: str | None):
    failures: list[str] = []
    durations: list[float] = []
    for index, (request, candidate) in enumerate(cases, start=1):
        started = time.perf_counter()
        actual = await baml_task.CheckTaskCompletion_async(
            "The user received a useful spoken reply that answered or responded "
            "to their message.",
            f'The agent_reply action returned text "{candidate}" and completed '
            'with status "ok".',
            current_user_request=request,
            current_conversation=_conversation(request, candidate),
            **client_kwargs(client_name),
        )
        durations.append(time.perf_counter() - started)
        if actual != baml_task.CompletionResult.PASS:
            failures.append(f"{request} | candidate={candidate} | actual={actual.value}")
        if index % 5 == 0 or index == len(cases):
            print(
                f"checked {index:,}/{len(cases):,}; false_failures={len(failures):,}",
                flush=True,
            )
    return failures, durations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--client")
    args = parser.parse_args()
    cases = NORMAL_COMPLETION_CASES
    if args.limit is not None:
        if not 1 <= args.limit <= len(cases):
            parser.error(f"--limit must be between 1 and {len(cases):,}")
        cases = cases[: args.limit]
    failures, durations = asyncio.run(_run(cases, args.client))
    average = sum(durations) / len(durations)
    print(
        f"average_seconds={average:.3f}; max_seconds={max(durations):.3f}; "
        f"under_5_seconds={sum(value < 5 for value in durations):,}/"
        f"{len(durations):,}",
        flush=True,
    )
    if failures:
        print("\n".join(failures))
        return 1
    print(f"passed {len(cases):,}/{len(cases):,} normal completion decisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
