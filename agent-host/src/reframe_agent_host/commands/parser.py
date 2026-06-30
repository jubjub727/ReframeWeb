from __future__ import annotations

import argparse

from reframe_agent_host import __version__
from reframe_agent_host.baml_client import types
from reframe_agent_host.commands.voice_args import add_voice_turn_args
from reframe_agent_host.speech.transcription import (
    DEFAULT_GPU_COMPUTE_TYPE,
    GPU_COMPUTE_TYPES,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reframe-agent-host",
        description="ReframeWeb Python Agent Host.",
    )
    parser.add_argument("--version", action="version", version=__version__)

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Verify the installed Agent Host stack.")
    subparsers.add_parser("audio-devices", help="List available microphone devices.")
    _add_gpu_check_parser(subparsers)
    _add_plan_turn_parser(subparsers)
    _add_debug_wake_audio_parser(subparsers)
    _add_voice_turn_parser(subparsers)
    return parser


def _add_gpu_check_parser(subparsers) -> None:
    gpu_check = subparsers.add_parser(
        "gpu-check",
        help="Verify the required CUDA faster-whisper runtime.",
    )
    gpu_check.add_argument(
        "--whisper-compute-type",
        choices=GPU_COMPUTE_TYPES,
        default=DEFAULT_GPU_COMPUTE_TYPE,
    )


def _add_plan_turn_parser(subparsers) -> None:
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


def _add_voice_turn_parser(subparsers) -> None:
    voice_turn = subparsers.add_parser(
        "voice-turn",
        help="Listen for one utterance, transcribe it, and optionally run BAML.",
    )
    voice_turn.add_argument(
        "--mode",
        choices=[mode.value for mode in types.ConversationMode],
        default=types.ConversationMode.WakeCommand.value,
    )
    voice_turn.add_argument(
        "--playback",
        choices=[state.value for state in types.PlaybackState],
        default=types.PlaybackState.Idle.value,
    )
    add_voice_turn_args(voice_turn)


def _add_debug_wake_audio_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "debug-wake-audio",
        help="Replay WAVs through local wake phrase detection only.",
    )
    parser.add_argument("wav", nargs="+")
    parser.add_argument("--wake-keyword", action="append", default=["jarvis"])
    parser.add_argument(
        "--conversation-on-phrase",
        action="append",
        default=["conversation on"],
    )
    parser.add_argument("--wake-gain", type=float, default=1.0)
    parser.add_argument("--window-ms", type=int, default=2000)
    parser.add_argument("--chunk-ms", type=int, default=32)
    parser.add_argument("--check-ms", type=int, default=160)
