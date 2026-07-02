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
    subparsers.add_parser("memory-setup", help="Apply memory schema and root nodes.")
    subparsers.add_parser("seed-core-tasks", help="Create the built-in core task memories.")
    subparsers.add_parser(
        "seed-opencode-go-providers",
        help="Create OpenCode Go model provider memories.",
    )
    subparsers.add_parser(
        "list-opencode-go-models",
        help="List the OpenCode Go model inventory used by BAML providers.",
    )
    _add_gpu_check_parser(subparsers)
    _add_choose_task_parser(subparsers)
    _add_benchmark_task_choice_parser(subparsers)
    _add_benchmark_conversation_evaluation_parser(subparsers)
    _add_analyze_task_choice_benchmark_parser(subparsers)
    _add_analyze_conversation_evaluation_benchmark_parser(subparsers)
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


def _add_choose_task_parser(subparsers) -> None:
    choose_task = subparsers.add_parser(
        "choose-task",
        help="Choose the first task for a transcript.",
    )
    choose_task.add_argument("transcript")
    choose_task.add_argument(
        "--session-id",
        help="Active memory_node session id used for conversation and session memory context.",
    )
    choose_task.add_argument(
        "--client",
        help="Optional BAML client name to benchmark or test instead of the function default.",
    )


def _add_benchmark_task_choice_parser(subparsers) -> None:
    benchmark = subparsers.add_parser(
        "benchmark-task-choice",
        help="Measure task-choice correctness and latency across direct model providers.",
    )
    benchmark.add_argument(
        "--session-id",
        help="Active memory_node session id used for conversation and session memory context.",
    )
    benchmark.add_argument(
        "--provider-id",
        action="append",
        dest="provider_ids",
        help="Direct model provider memory_node id to test. Repeat to test a subset.",
    )
    benchmark.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Benchmark case id to run. Repeat to test a subset.",
    )
    benchmark.add_argument("--runs", type=int, default=1)
    benchmark.add_argument("--warmup-runs", type=int, default=0)
    benchmark.add_argument("--delay-seconds", type=float, default=2.0)
    benchmark.add_argument("--provider-cooldown-seconds", type=float, default=8.0)
    benchmark.add_argument(
        "--output",
        help="Path to write benchmark JSON. Defaults to benchmark-results/task-choice-<timestamp>.json.",
    )


def _add_benchmark_conversation_evaluation_parser(subparsers) -> None:
    benchmark = subparsers.add_parser(
        "benchmark-conversation-evaluation",
        help="Record conversation-evaluation memory-search hints across models.",
    )
    benchmark.add_argument(
        "--provider-id",
        action="append",
        dest="provider_ids",
        help="Direct model provider memory_node id to test. Repeat to test a subset.",
    )
    benchmark.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Benchmark case id to run. Repeat to test a subset.",
    )
    benchmark.add_argument("--runs", type=int, default=1)
    benchmark.add_argument("--warmup-runs", type=int, default=0)
    benchmark.add_argument("--delay-seconds", type=float, default=2.0)
    benchmark.add_argument("--provider-cooldown-seconds", type=float, default=8.0)
    benchmark.add_argument(
        "--output",
        help=(
            "Path to write benchmark JSON. Defaults to "
            "benchmark-results/conversation-evaluation-<timestamp>.json."
        ),
    )


def _add_analyze_task_choice_benchmark_parser(subparsers) -> None:
    analyze = subparsers.add_parser(
        "analyze-task-choice-benchmark",
        help="Summarize failures from a saved task-choice benchmark JSON file.",
    )
    analyze.add_argument("path")


def _add_analyze_conversation_evaluation_benchmark_parser(subparsers) -> None:
    analyze = subparsers.add_parser(
        "analyze-conversation-evaluation-benchmark",
        aliases=["analyse-conversation-evaluation-benchmark"],
        help="Show conversation-evaluation replies ordered by latency.",
    )
    analyze.add_argument("path")


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
