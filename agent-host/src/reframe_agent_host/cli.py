from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
from typing import Sequence

from reframe_agent_host import __version__
from reframe_agent_host.baml_client import b, types


DEPENDENCY_IMPORTS: tuple[tuple[str, str], ...] = (
    ("baml-py", "baml_py"),
    ("sounddevice", "sounddevice"),
    ("pvporcupine", "pvporcupine"),
    ("silero-vad", "silero_vad"),
    ("faster-whisper", "faster_whisper"),
    ("kokoro", "kokoro"),
)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="reframe-agent-host",
        description="ReframeWeb Python Agent Host.",
    )
    parser.add_argument("--version", action="version", version=__version__)

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Verify the installed Agent Host stack.")

    plan_turn = subparsers.add_parser(
        "plan-turn",
        help="Run the first BAML conversation-turn planner from a transcript.",
    )
    plan_turn.add_argument("transcript")
    plan_turn.add_argument(
        "--mode",
        choices=[mode.value for mode in types.ConversationMode],
        default=types.ConversationMode.WakeCommand.value,
    )
    plan_turn.add_argument(
        "--playback",
        choices=[state.value for state in types.PlaybackState],
        default=types.PlaybackState.Idle.value,
    )

    args = parser.parse_args(argv)

    if args.command == "doctor":
        raise SystemExit(_doctor())

    if args.command == "plan-turn":
        raise SystemExit(
            asyncio.run(
                _plan_turn(
                    transcript=args.transcript,
                    mode=types.ConversationMode(args.mode),
                    playback_state=types.PlaybackState(args.playback),
                )
            )
        )

    parser.error(f"Unknown command: {args.command}")


def _doctor() -> int:
    missing: list[str] = []

    print(f"reframe-agent-host {__version__}")
    for package_name, module_name in DEPENDENCY_IMPORTS:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(package_name)
            print(f"[missing] {package_name}")
        else:
            print(f"[ok]      {package_name}")

    for env_name in ("OPENCODE_GO_API_KEY",):
        status = "set" if os.getenv(env_name) else "not set"
        print(f"[env]     {env_name}: {status}")

    return 1 if missing else 0


async def _plan_turn(
    transcript: str,
    mode: types.ConversationMode,
    playback_state: types.PlaybackState,
) -> int:
    result = await b.PlanConversationTurn(
        transcript=transcript,
        conversation_mode=mode,
        playback_state=playback_state,
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0
