from __future__ import annotations

import argparse

from reframe_agent_host.speech.transcription import (
    DEFAULT_GPU_COMPUTE_TYPE,
    GPU_COMPUTE_TYPES,
)


def add_voice_turn_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--device", help="Input device index or name.")
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16_000,
        help="Processing sample rate for VAD, wake detection, and Whisper.",
    )
    parser.add_argument(
        "--input-sample-rate",
        type=int,
        default=0,
        help="Microphone stream rate. 0 opens the selected device at its native rate.",
    )
    parser.add_argument(
        "--input-gain",
        type=float,
        default=1.0,
        help="Gain applied to captured mic audio before wake detection and transcription.",
    )
    parser.add_argument(
        "--input-channels",
        type=int,
        default=0,
        help="Microphone channels to request. 0 uses up to two native channels.",
    )
    parser.add_argument(
        "--input-channel",
        type=int,
        default=0,
        help="Zero-based captured channel to process.",
    )
    parser.add_argument("--chunk-ms", type=int, default=32)
    parser.add_argument(
        "--wake-keyword",
        action="append",
        default=["jarvis"],
        help="Local wake keyphrase. Can be repeated.",
    )
    parser.add_argument(
        "--conversation-on-phrase",
        action="append",
        default=["conversation on"],
        help="Local phrase that switches to continuous conversation mode.",
    )
    parser.add_argument(
        "--conversation-on-confirm-window-ms",
        type=int,
        default=2000,
        help="Rolling audio window used to confirm the full phrase.",
    )
    parser.add_argument(
        "--wake-check-ms",
        type=int,
        default=320,
        help="How often to run local wake phrase recognition.",
    )
    parser.add_argument(
        "--wake-gain",
        type=float,
        default=1.0,
        help="Input gain applied only to local keyphrase detection.",
    )
    parser.add_argument(
        "--wake-threshold",
        type=float,
        default=1e-30,
        help="PocketSphinx KWS threshold used to confirm wake-keyword candidates.",
    )
    parser.add_argument(
        "--wake-carry-ms",
        type=int,
        default=2000,
        help="Recent audio replayed after wake detection to avoid clipping commands.",
    )
    parser.add_argument(
        "--wake-replay-pre-ms",
        type=int,
        default=80,
        help="Audio kept before the detected wake phrase ends when replaying into VAD.",
    )
    parser.add_argument(
        "--vad",
        choices=["auto", "silero", "energy"],
        default="auto",
        help="Voice activity detector to use.",
    )
    parser.add_argument("--vad-threshold", type=float, default=0.35)
    parser.add_argument("--min-silence-ms", type=int, default=0)
    parser.add_argument("--speech-pad-ms", type=int, default=0)
    parser.add_argument("--pre-speech-ms", type=int, default=320)
    parser.add_argument("--min-utterance-ms", type=int, default=250)
    parser.add_argument("--max-utterance-seconds", type=float, default=20.0)
    parser.add_argument("--energy-start-threshold", type=float, default=0.012)
    parser.add_argument("--energy-end-threshold", type=float, default=0.008)
    parser.add_argument("--listen-timeout-seconds", type=float, default=0.0)
    parser.add_argument(
        "--debug-audio-dir",
        help="Opt-in directory for saving local wake/debug WAV clips.",
    )
    parser.add_argument(
        "--debug-audio-seconds",
        type=float,
        default=8.0,
        help="Seconds of rolling mic audio to keep for debug clips.",
    )
    parser.add_argument(
        "--debug-audio-period-seconds",
        type=float,
        default=0.0,
        help="Opt-in interval for saving rolling debug clips while waiting.",
    )
    parser.add_argument(
        "--post-activation-command-window-ms",
        type=int,
        default=700,
        help=(
            "After 'conversation on', wait this long for same-utterance command "
            "speech before returning a mode-only switch."
        ),
    )
    parser.add_argument("--whisper-model", default="base.en")
    parser.add_argument(
        "--whisper-compute-type",
        choices=GPU_COMPUTE_TYPES,
        default=DEFAULT_GPU_COMPUTE_TYPE,
    )
    parser.add_argument("--language", default="en")
    parser.add_argument("--beam-size", type=int, default=1)
    parser.add_argument(
        "--session-id",
        help="Active memory_node session id used for conversation and session memory context.",
    )
    parser.add_argument(
        "--conversation-id",
        help=(
            "Active memory_node conversation id used to record this voice turn. "
            "Created automatically when omitted."
        ),
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=0,
        help="Number of voice turns to run. Default 0 keeps listening until Ctrl+C.",
    )
    parser.add_argument(
        "--no-task-choice",
        action="store_true",
        help="Stop after transcription instead of choosing an initial task with BAML.",
    )
    parser.add_argument(
        "--debug-output",
        action="store_true",
        help="Print pipeline stages, ids, timing, and compact diagnostics.",
    )
    parser.add_argument(
        "--verbose-context",
        action="store_true",
        help="Print retrieved memories, task catalog, and conversation context.",
    )
