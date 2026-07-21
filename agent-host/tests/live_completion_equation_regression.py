from __future__ import annotations

import argparse
import asyncio
import time

from baml_sdk import task as baml_task
from baml_sdk import turn_context as baml_turn_context

from reframe_agent_host.agent_flow.provider_clients import client_kwargs

from tests.completion_equation_case_types import EquationCase
from tests.completion_equation_cases import ALL_EQUATION_CASES, USER_TRANSCRIPT_CASES


COMPLETION_REQUIREMENT = (
    "The user received a useful spoken reply that answered or responded to "
    "their message."
)


def _conversation(case: EquationCase, candidate: str):
    historical = [value for value in case.alternatives if value != candidate]
    if len(historical) < 2:
        historical = list(case.alternatives[:2])
    return baml_turn_context.ConversationHistory(
        id="equation-validation",
        name="Equation validation",
        created_at="2026-07-21T00:00:00Z",
        updated_at="2026-07-21T00:00:04Z",
        read_at="2026-07-21T00:00:04Z",
        messages=[
            baml_turn_context.ConversationHistoryMessage(
                created_at="2026-07-21T00:00:00Z",
                updated_at="2026-07-21T00:00:00Z",
                read_at="2026-07-21T00:00:00Z",
                role="human",
                content=case.request,
            ),
            baml_turn_context.ConversationHistoryMessage(
                created_at="2026-07-21T00:00:01Z",
                updated_at="2026-07-21T00:00:01Z",
                read_at="2026-07-21T00:00:01Z",
                role="agent",
                content=historical[0],
            ),
            baml_turn_context.ConversationHistoryMessage(
                created_at="2026-07-21T00:00:02Z",
                updated_at="2026-07-21T00:00:02Z",
                read_at="2026-07-21T00:00:02Z",
                role="validation_reply",
                content=f"A previous check claimed {historical[1]}.",
            ),
            baml_turn_context.ConversationHistoryMessage(
                created_at="2026-07-21T00:00:03Z",
                updated_at="2026-07-21T00:00:03Z",
                read_at="2026-07-21T00:00:03Z",
                role="agent",
                content=candidate,
            ),
        ],
    )


async def _run(
    cases: tuple[EquationCase, ...],
    candidate_mode: str,
    client_name: str | None,
) -> tuple[list[str], int, list[float]]:
    failures: list[str] = []
    durations: list[float] = []
    candidates_per_case = {"all": 4, "accepted": 1, "alternatives": 3}[
        candidate_mode
    ]
    total = len(cases) * candidates_per_case
    completed = 0
    for case in cases:
        candidates = (
            case.candidates
            if candidate_mode == "all"
            else (case.reference,)
            if candidate_mode == "accepted"
            else case.alternatives
        )
        for candidate in candidates:
            expected = (
                baml_task.CompletionResult.PASS
                if candidate == case.reference
                else baml_task.CompletionResult.FAIL
            )
            started = time.perf_counter()
            actual = await baml_task.CheckTaskCompletion_async(
                COMPLETION_REQUIREMENT,
                f'The agent_reply action returned text "{candidate}" '
                'and completed with status "ok".',
                current_user_request=case.request,
                current_conversation=_conversation(case, candidate),
                **client_kwargs(client_name),
            )
            durations.append(time.perf_counter() - started)
            completed += 1
            if actual != expected:
                failures.append(
                    f"{case.request} | candidate={candidate} | "
                    f"expected={expected.value} | actual={actual.value}"
                )
            if completed % 10 == 0 or completed == total:
                print(
                    f"checked {completed:,}/{total:,}; failures={len(failures):,}",
                    flush=True,
                )
    return failures, total, durations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("all", "user"), default="all")
    parser.add_argument("--case-number", type=int)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument(
        "--candidate-mode",
        choices=("all", "accepted", "alternatives"),
        default="all",
    )
    parser.add_argument("--client")
    args = parser.parse_args()
    cases = ALL_EQUATION_CASES if args.scope == "all" else USER_TRANSCRIPT_CASES
    if args.case_number is not None:
        if not 1 <= args.case_number <= len(cases):
            parser.error(f"--case-number must be between 1 and {len(cases):,}")
        cases = (cases[args.case_number - 1],)
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    cases = cases * args.repeat
    failures, total, durations = asyncio.run(
        _run(cases, args.candidate_mode, args.client)
    )
    print(
        f"average_seconds={sum(durations) / len(durations):.3f}; "
        f"max_seconds={max(durations):.3f}; "
        f"under_5_seconds={sum(value < 5 for value in durations):,}/"
        f"{len(durations):,}",
        flush=True,
    )
    if failures:
        print("\n".join(failures))
        return 1
    print(
        f"passed {total:,}/{total:,} live validation decisions",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
