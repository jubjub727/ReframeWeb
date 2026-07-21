from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import time

from baml_sdk import task as baml_task
from baml_sdk import turn_context as baml_turn_context

from reframe_agent_host.agent_flow.provider_clients import client_kwargs


@dataclass(frozen=True, slots=True)
class ValidationCase:
    request: str
    accepted: str
    alternatives: tuple[str, str, str]

    @property
    def candidates(self) -> tuple[str, str, str, str]:
        return (self.accepted, *self.alternatives)


CASES = (
    ValidationCase(
        "Reverse the exact text Agent-42 and reply with only the reversed text.",
        "24-tnegA",
        ("24-tnega", "Agent-42", "24-Agent"),
    ),
    ValidationCase(
        "Reply with a JSON object containing exactly two keys: enabled set to "
        "true and retries set to 3.",
        '{"enabled":true,"retries":3}',
        (
            '{"enabled":true,"retries":4}',
            '{"enabled":true}',
            '{"enabled":"true","retries":3}',
        ),
    ),
    ValidationCase(
        "Name the two mammals in this list: whale, trout, eagle, bat.",
        "whale and bat",
        ("whale and eagle", "whale", "trout and eagle"),
    ),
    ValidationCase(
        "From this sentence—'Three amber lamps stand beside one silver "
        "chair'—reply with the lamp count and lamp color, in that order.",
        "three, amber",
        ("one, amber", "three, silver", "amber, three"),
    ),
    ValidationCase(
        "In one sentence, explain why regular backups matter.",
        "Regular backups let people recover data after loss, corruption, or "
        "accidental deletion.",
        (
            "Regular backups make a computer's processor run faster.",
            "Regular backups matter.",
            "Backups permanently prevent all data loss.",
        ),
    ),
    ValidationCase(
        "Provide a JavaScript expression that returns the number of items in "
        "an array named items.",
        "items.length",
        ("items.size", "items.length()", "length(items)"),
    ),
    ValidationCase(
        "Summarize this in one sentence: 'Maya missed the bus, called a taxi, "
        "and arrived before the doors closed.'",
        "After missing the bus, Maya took a taxi and arrived before the doors "
        "closed.",
        (
            "Maya arrived after the doors closed.",
            "Maya missed the bus.",
            "Maya drove herself and arrived early.",
        ),
    ),
)


def _conversation(case: ValidationCase, candidate: str):
    history = [value for value in case.alternatives if value != candidate]
    if len(history) < 2:
        history = list(case.alternatives[:2])
    messages = [
        ("human", case.request),
        ("agent", history[0]),
        ("validation_reply", f"A previous check claimed: {history[1]}"),
        ("agent", candidate),
    ]
    return baml_turn_context.ConversationHistory(
        id="generic-validation",
        name="Generic validation",
        created_at="2026-07-21T00:00:00Z",
        updated_at="2026-07-21T00:00:04Z",
        read_at="2026-07-21T00:00:04Z",
        messages=[
            baml_turn_context.ConversationHistoryMessage(
                created_at=f"2026-07-21T00:00:0{index}Z",
                updated_at=f"2026-07-21T00:00:0{index}Z",
                read_at=f"2026-07-21T00:00:0{index}Z",
                role=role,
                content=content,
            )
            for index, (role, content) in enumerate(messages)
        ],
    )


async def _run(client_name: str | None) -> tuple[list[str], list[float]]:
    failures: list[str] = []
    durations: list[float] = []
    for case in CASES:
        for candidate in case.candidates:
            expected = (
                baml_task.CompletionResult.PASS
                if candidate == case.accepted
                else baml_task.CompletionResult.FAIL
            )
            started = time.perf_counter()
            actual = await baml_task.CheckTaskCompletion_async(
                "The user received a useful reply that fulfilled their request.",
                f'The agent_reply action returned text "{candidate}" and '
                'completed with status "ok".',
                current_user_request=case.request,
                current_conversation=_conversation(case, candidate),
                **client_kwargs(client_name),
            )
            durations.append(time.perf_counter() - started)
            if actual != expected:
                failures.append(
                    f"{case.request} | candidate={candidate} | "
                    f"expected={expected.value} | actual={actual.value}"
                )
    return failures, durations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client")
    args = parser.parse_args()
    failures, durations = asyncio.run(_run(args.client))
    print(
        f"average_seconds={sum(durations) / len(durations):.3f}; "
        f"max_seconds={max(durations):.3f}; "
        f"under_5_seconds={sum(value < 5 for value in durations):,}/"
        f"{len(durations):,}"
    )
    if failures:
        print("\n".join(failures))
        return 1
    total = len(CASES) * 4
    print(f"passed {total:,}/{total:,} generic live validation decisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
