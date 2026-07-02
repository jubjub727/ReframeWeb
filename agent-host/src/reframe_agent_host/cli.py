from __future__ import annotations

import asyncio
from typing import Sequence

from reframe_agent_host.commands.checks import (
    run_audio_devices,
    run_doctor,
    run_gpu_check,
)
from reframe_agent_host.commands.conversation_evaluation import (
    run_analyze_conversation_evaluation_benchmark,
    run_benchmark_conversation_evaluation,
)
from reframe_agent_host.commands.parser import build_parser
from reframe_agent_host.commands.task_choice import (
    run_benchmark_task_choice,
    run_analyze_task_choice_benchmark,
    run_choose_task,
    run_list_opencode_go_models,
    run_memory_setup,
    run_seed_core_tasks,
    run_seed_opencode_go_providers,
)
from reframe_agent_host.commands.voice_turn import run_voice_turn
from reframe_agent_host.commands.debug_wake_audio import run_debug_wake_audio


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        raise SystemExit(run_doctor())

    if args.command == "audio-devices":
        raise SystemExit(run_audio_devices())

    if args.command == "memory-setup":
        raise SystemExit(asyncio.run(run_memory_setup()))

    if args.command == "seed-core-tasks":
        raise SystemExit(asyncio.run(run_seed_core_tasks()))

    if args.command == "seed-opencode-go-providers":
        raise SystemExit(asyncio.run(run_seed_opencode_go_providers()))

    if args.command == "list-opencode-go-models":
        raise SystemExit(run_list_opencode_go_models())

    if args.command == "analyze-task-choice-benchmark":
        raise SystemExit(run_analyze_task_choice_benchmark(args.path))

    if args.command in (
        "analyze-conversation-evaluation-benchmark",
        "analyse-conversation-evaluation-benchmark",
    ):
        raise SystemExit(run_analyze_conversation_evaluation_benchmark(args.path))

    if args.command == "gpu-check":
        raise SystemExit(run_gpu_check(args.whisper_compute_type))

    if args.command == "choose-task":
        raise SystemExit(
            asyncio.run(
                run_choose_task(
                    transcript=args.transcript,
                    session_id=args.session_id,
                    client_name=args.client,
                ),
            )
        )

    if args.command == "benchmark-task-choice":
        if args.runs < 1:
            parser.error("--runs must be at least 1")
        if args.warmup_runs < 0:
            parser.error("--warmup-runs cannot be negative")
        if args.delay_seconds < 0:
            parser.error("--delay-seconds cannot be negative")
        if args.provider_cooldown_seconds < 0:
            parser.error("--provider-cooldown-seconds cannot be negative")
        raise SystemExit(
            asyncio.run(
                run_benchmark_task_choice(
                    session_id=args.session_id,
                    runs=args.runs,
                    warmup_runs=args.warmup_runs,
                    delay_seconds=args.delay_seconds,
                    provider_cooldown_seconds=args.provider_cooldown_seconds,
                    provider_ids=args.provider_ids,
                    case_ids=args.case_ids,
                    output=args.output,
                ),
            )
        )

    if args.command == "benchmark-conversation-evaluation":
        if args.runs < 1:
            parser.error("--runs must be at least 1")
        if args.warmup_runs < 0:
            parser.error("--warmup-runs cannot be negative")
        if args.delay_seconds < 0:
            parser.error("--delay-seconds cannot be negative")
        if args.provider_cooldown_seconds < 0:
            parser.error("--provider-cooldown-seconds cannot be negative")
        raise SystemExit(
            asyncio.run(
                run_benchmark_conversation_evaluation(
                    runs=args.runs,
                    warmup_runs=args.warmup_runs,
                    delay_seconds=args.delay_seconds,
                    provider_cooldown_seconds=args.provider_cooldown_seconds,
                    provider_ids=args.provider_ids,
                    case_ids=args.case_ids,
                    output=args.output,
                ),
            )
        )

    if args.command == "debug-wake-audio":
        raise SystemExit(run_debug_wake_audio(args))

    if args.command == "voice-turn":
        raise SystemExit(asyncio.run(run_voice_turn(args)))

    parser.error(f"Unknown command: {args.command}")
