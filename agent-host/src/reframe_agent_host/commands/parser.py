from __future__ import annotations

import argparse

from baml_sdk import turn_context as baml_turn_context

from reframe_agent_host import __version__
from reframe_agent_host.commands.benchmark_args import add_benchmark_parsers
from reframe_agent_host.commands.voice_args import add_voice_turn_args
from reframe_agent_host.speech.transcription import (
    DEFAULT_CPU_COMPUTE_TYPE,
    TRANSCRIPTION_BACKENDS,
    TRANSCRIPTION_COMPUTE_TYPES,
    TRANSCRIPTION_DEVICES,
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
    subparsers.add_parser("memory-setup", help="Apply memory schema and root nodes.")
    _add_memory_browser_parser(subparsers)
    subparsers.add_parser("seed-core-tasks", help="Create the built-in core tasks.")
    subparsers.add_parser(
        "seed-opencode-go-providers",
        help="Create OpenCode Go model providers.",
    )
    subparsers.add_parser(
        "list-opencode-go-models",
        help="List the OpenCode Go model inventory used by BAML providers.",
    )
    _add_transcription_check_parser(subparsers)
    _add_audio_quality_test_parser(subparsers)
    _add_choose_task_parser(subparsers)
    add_benchmark_parsers(subparsers)
    _add_debug_wake_audio_parser(subparsers)
    _add_record_wake_audio_parser(subparsers)
    _add_voice_turn_parser(subparsers)
    return parser


def _add_transcription_check_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "transcription-check",
        aliases=["gpu-check"],
        help="Verify the configured local transcription runtime.",
    )
    parser.add_argument("--transcriber", choices=TRANSCRIPTION_BACKENDS, default="auto")
    parser.add_argument(
        "--transcriber-device", choices=TRANSCRIPTION_DEVICES, default="auto"
    )
    parser.add_argument(
        "--whisper-compute-type",
        choices=TRANSCRIPTION_COMPUTE_TYPES,
        default="auto",
    )
    parser.add_argument(
        "--whisper-cpu-compute-type",
        choices=TRANSCRIPTION_COMPUTE_TYPES,
        default=DEFAULT_CPU_COMPUTE_TYPE,
    )
    parser.add_argument(
        "--whisper-cpp-bin",
        help="Path to whisper.cpp whisper-cli. Defaults to PATH discovery.",
    )
    parser.add_argument("--whisper-cpp-model", help="Path to a whisper.cpp ggml model.")
    parser.add_argument(
        "--no-cpu-fallback",
        action="store_true",
        help="Fail instead of falling back to faster-whisper CPU transcription.",
    )


def _add_audio_quality_test_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "audio-quality-test",
        help="Record one microphone sample and verify it is loud enough for ASR.",
    )
    parser.add_argument("--device", help="Input device index or name.")
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--sample-rate", type=int, default=16_000)
    parser.add_argument("--input-sample-rate", type=int, default=0)
    parser.add_argument("--input-gain", type=float, default=1.0)
    parser.add_argument("--limiter-ceiling", type=float, default=0.95)
    parser.add_argument("--input-channels", type=int, default=0)
    parser.add_argument("--input-channel", type=int, default=-1)
    parser.add_argument("--chunk-ms", type=int, default=32)
    parser.add_argument("--countdown-seconds", type=float, default=1.0)
    parser.add_argument("--output-dir", default=".debug-audio-quality")
    parser.add_argument("--prompt", default="tell me a joke")
    parser.add_argument("--no-prompt", action="store_true")
    parser.add_argument("--save-calibration", action="store_true")
    parser.add_argument("--use-calibration", action="store_true")
    parser.add_argument(
        "--calibration-file",
        default=".reframe-audio-calibration.json",
    )


def _add_memory_browser_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "memory-browser",
        help="Start a local visual browser for the Reframe memory database.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)


def _add_choose_task_parser(subparsers) -> None:
    parser = subparsers.add_parser("choose-task", help="Choose a task for a transcript.")
    parser.add_argument("transcript")
    parser.add_argument("--session-id", help="Active session id for memory context.")
    parser.add_argument(
        "--conversation-id",
        help="Active conversation id within the supplied session.",
    )
    parser.add_argument("--client", help="Optional BAML client override.")


def _add_voice_turn_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "voice-turn",
        help="Listen for utterances, transcribe them, and run the agent flow.",
    )
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in baml_turn_context.ConversationMode],
        default=baml_turn_context.ConversationMode.WAKE_COMMAND.value,
    )
    add_voice_turn_args(parser)


def _add_debug_wake_audio_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "debug-wake-audio",
        help="Replay WAVs through local wake phrase detection only.",
    )
    parser.add_argument("wav", nargs="+")
    parser.add_argument("--wake-keyword", action="append", default=["jarvis"])
    parser.add_argument(
        "--conversation-on-phrase", action="append", default=["conversation on"]
    )
    parser.add_argument("--wake-gain", type=float, default=1.0)
    parser.add_argument("--wake-threshold", type=float, default=1e-30)
    parser.add_argument("--window-ms", type=int, default=2000)
    parser.add_argument("--chunk-ms", type=int, default=32)
    parser.add_argument("--check-ms", type=int, default=160)


def _add_record_wake_audio_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "record-wake-audio",
        help="Record labeled microphone clips for wake detection debugging.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=None,
        help="Labeled case in label:spoken text form. Repeat as needed.",
    )
    parser.add_argument("--output-dir", default=".debug-wake-tests")
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--countdown-seconds", type=float, default=1.0)
    parser.add_argument("--no-prompt", action="store_true")
    parser.add_argument("--device", help="Input device index or name.")
    parser.add_argument("--sample-rate", type=int, default=16_000)
    parser.add_argument("--input-sample-rate", type=int, default=0)
    parser.add_argument("--input-gain", type=float, default=1.0)
    parser.add_argument("--input-channels", type=int, default=0)
    parser.add_argument("--input-channel", type=int, default=-1)
    parser.add_argument("--chunk-ms", type=int, default=32)
