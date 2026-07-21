from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time

from baml_sdk import task as baml_task
from baml_sdk import turn_context as baml_turn_context


@dataclass(frozen=True, slots=True)
class WrapperCase:
    name: str
    request: str
    candidate: str
    output_summary: str
    expected: baml_task.CompletionResult
    required: bool = True


def _conversation(case: WrapperCase):
    return baml_turn_context.ConversationHistory(
        id=f"wrapper-{case.name}",
        name="Delivery wrapper validation",
        created_at="2026-07-21T00:00:00Z",
        updated_at="2026-07-21T00:00:02Z",
        read_at="2026-07-21T00:00:02Z",
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
                content=case.candidate,
            ),
        ],
    )


def _cases() -> tuple[WrapperCase, ...]:
    oversized_candidate = f"{5**2048 + 3:,}"
    return (
        WrapperCase(
            "agent-reply-number",
            "What is five plus eight? Reply with the answer only.",
            "13",
            'The agent_reply action returned text "13" and status "ok".',
            baml_task.CompletionResult.PASS,
        ),
        WrapperCase(
            "agent-message-number",
            "What is five plus eight? Reply with the answer only.",
            "13",
            'agent_message returned payload {"text":"13"}.',
            baml_task.CompletionResult.PASS,
        ),
        WrapperCase(
            "return-item-reversal",
            "Reverse Agent-42 and return only the reversed text.",
            "24-tnegA",
            'returns[0] was agent_reply with payload {"text":"24-tnegA"}.',
            baml_task.CompletionResult.PASS,
        ),
        WrapperCase(
            "json-payload",
            "Return only a JSON object with enabled set to true.",
            '{"enabled":true}',
            'The agent_message item completed successfully with payload '
            '{"text":"{\\"enabled\\":true}"}.',
            baml_task.CompletionResult.PASS,
        ),
        WrapperCase(
            "ordinary-reply",
            "Tell me a short clock joke.",
            "I tried to make a belt from watches, but it was a waist of time.",
            "An agent_reply message was posted with text payload: I tried to "
            "make a belt from watches, but it was a waist of time.",
            baml_task.CompletionResult.PASS,
        ),
        WrapperCase(
            "wrong-sum",
            "What is 5 to the power of 24 plus 8? Reply with the answer only.",
            "59,604,644,775,390,625",
            "The agent_reply action returned text "
            '"59,604,644,775,390,625" and completed with status "ok".',
            baml_task.CompletionResult.FAIL,
        ),
        WrapperCase(
            "wrong-reversal",
            "Reverse Agent-42 and return only the reversed text.",
            "24-Agent",
            'agent_message returned payload {"text":"24-Agent"}.',
            baml_task.CompletionResult.FAIL,
        ),
        WrapperCase(
            "wrong-json-value",
            "Return only a JSON object with enabled set to true.",
            '{"enabled":false}',
            'returns[0] was agent_reply with payload '
            '{"text":"{\\"enabled\\":false}"}.',
            baml_task.CompletionResult.FAIL,
        ),
        WrapperCase(
            "missing-part",
            "Name the two mammals in this list: whale, trout, eagle, bat.",
            "whale",
            'The agent_reply action returned text "whale" and status "ok".',
            baml_task.CompletionResult.FAIL,
        ),
        WrapperCase(
            "oversized-power-result",
            "What is 5 to the power of 256 plus 3? Reply with the answer only.",
            oversized_candidate,
            f'agent_message returned payload {{"text":"{oversized_candidate}"}}.',
            baml_task.CompletionResult.FAIL,
            required=False,
        ),
    )


async def _check_gate() -> tuple[list[str], list[float]]:
    failures: list[str] = []
    observations: list[str] = []
    durations: list[float] = []
    for case in _cases():
        started = time.perf_counter()
        actual = await baml_task.CheckTaskCompletion_async(
            "The user received the requested reply.",
            case.output_summary,
            current_user_request=case.request,
            current_conversation=_conversation(case),
        )
        durations.append(time.perf_counter() - started)
        if actual != case.expected:
            mismatch = (
                f"{case.name}: expected={case.expected.value}, actual={actual.value}"
            )
            if case.required:
                failures.append(mismatch)
            else:
                observations.append(f"non-blocking hard probe: {mismatch}")
        print(
            f"{case.name}: expected={case.expected.value}, actual={actual.value}",
            flush=True,
        )
    for observation in observations:
        print(observation, flush=True)
    return failures, durations


async def _check_guidance() -> tuple[list[str], list[float]]:
    failures: list[str] = []
    durations: list[float] = []
    task_prompt = """Answer the human directly using the supplied request.

Allowed return items:
- agent_reply with payload {"text": "..."} for the message the user should hear.

Input:
What is 5 to the power of 24 plus 8? Reply with the answer only."""
    summary = (
        "The agent_reply action returned text "
        '"59,604,644,775,390,625" and completed with status "ok".'
    )
    forbidden = (
        "delivery channel",
        "wrapper",
        "spoken message",
        "agent_message",
        "bare numeric",
        "raw answer",
    )
    for index in range(3):
        started = time.perf_counter()
        decision = await baml_task.WriteValidationReply_async(
            task_prompt,
            "The user received the requested answer only.",
            summary,
            "",
        )
        durations.append(time.perf_counter() - started)
        lowered = decision.validation_reply.lower()
        found = [phrase for phrase in forbidden if phrase in lowered]
        if found:
            failures.append(
                f"guidance-{index + 1}: wrapper rationale remained: {found}"
            )
        print(f"guidance-{index + 1}: {decision.validation_reply}", flush=True)
    return failures, durations


async def _run() -> int:
    gate_failures, gate_durations = await _check_gate()
    guidance_failures, guidance_durations = await _check_guidance()
    durations = gate_durations + guidance_durations
    failures = gate_failures + guidance_failures
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
    print("passed 9/9 required wrapper decisions and 3/3 guidance checks")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
