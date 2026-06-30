from __future__ import annotations

import asyncio
from typing import Sequence

from reframe_agent_host.baml_client import types
from reframe_agent_host.commands.checks import (
    run_audio_devices,
    run_doctor,
    run_gpu_check,
)
from reframe_agent_host.commands.parser import build_parser
from reframe_agent_host.commands.plan import run_plan_turn
from reframe_agent_host.commands.voice_turn import run_voice_turn
from reframe_agent_host.commands.debug_wake_audio import run_debug_wake_audio


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        raise SystemExit(run_doctor())

    if args.command == "audio-devices":
        raise SystemExit(run_audio_devices())

    if args.command == "gpu-check":
        raise SystemExit(run_gpu_check(args.whisper_compute_type))

    if args.command == "plan-turn":
        raise SystemExit(
            asyncio.run(
                run_plan_turn(
                    transcript=args.transcript,
                    mode=types.ConversationMode(args.mode),
                    playback_state=types.PlaybackState(args.playback),
                )
            )
        )

    if args.command == "debug-wake-audio":
        raise SystemExit(run_debug_wake_audio(args))

    if args.command == "voice-turn":
        raise SystemExit(asyncio.run(run_voice_turn(args)))

    parser.error(f"Unknown command: {args.command}")
