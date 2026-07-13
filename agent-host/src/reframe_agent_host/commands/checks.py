from __future__ import annotations

import importlib
import os
import sys

from reframe_agent_host import __version__
from reframe_agent_host.voice.audio_devices import list_input_devices
from reframe_agent_host.speech.transcription import (
    TranscriptionRuntimeError,
    WhisperTranscriberConfig,
    validate_whisper_gpu_runtime,
    validate_transcription_runtime,
)


DEPENDENCY_IMPORTS: tuple[tuple[str, str], ...] = (
    ("baml-bridge", "baml_bridge"),
    ("numpy", "numpy"),
    ("sounddevice", "sounddevice"),
    ("pocketsphinx", "pocketsphinx"),
    ("silero-vad", "silero_vad"),
    ("faster-whisper", "faster_whisper"),
    ("kokoro-onnx", "kokoro_onnx"),
)


def run_doctor() -> int:
    missing: list[str] = []
    print(f"reframe-agent-host {__version__}")
    _print_dependency_status(missing)
    _print_environment_status()
    _print_transcription_status(missing)
    return 1 if missing else 0


def run_gpu_check(compute_type: str) -> int:
    if compute_type in {"auto", "default"}:
        compute_type = "float16"
    try:
        status = validate_whisper_gpu_runtime(compute_type)
    except TranscriptionRuntimeError as error:
        print(f"[missing] CUDA faster-whisper runtime: {error}", file=sys.stderr)
        return 1

    print("CUDA faster-whisper runtime ready")
    print(f"devices: {status.cuda_device_count}")
    print(f"compute_type: {status.compute_type}")
    print(f"supported_compute_types: {', '.join(status.supported_compute_types)}")
    return 0


def run_transcription_check(args) -> int:
    config = WhisperTranscriberConfig(
        backend=args.transcriber,
        device=args.transcriber_device,
        compute_type=args.whisper_compute_type,
        cpu_compute_type=args.whisper_cpu_compute_type,
        allow_cpu_fallback=not args.no_cpu_fallback,
        whisper_cpp_bin=args.whisper_cpp_bin,
        whisper_cpp_model=args.whisper_cpp_model,
    )
    try:
        status = validate_transcription_runtime(config)
    except TranscriptionRuntimeError as error:
        print(f"[missing] transcription runtime: {error}", file=sys.stderr)
        return 1

    _print_runtime_status("transcription runtime ready", status)
    return 0


def run_audio_devices() -> int:
    devices = list_input_devices()
    if not devices:
        print("No input devices found.")
        return 1

    for device in devices:
        marker = "*" if device.is_default_input else " "
        print(
            f"{marker} {device.index:>2}  {device.name} "
            f"[{device.host_api_name}] "
            f"({device.max_input_channels} in, {device.default_sample_rate:.0f} Hz)"
        )

    print("\n* = default input device")
    return 0


def _print_dependency_status(missing: list[str]) -> None:
    for package_name, module_name in DEPENDENCY_IMPORTS:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(package_name)
            print(f"[missing] {package_name}")
        else:
            print(f"[ok]      {package_name}")


def _print_environment_status() -> None:
    for env_name in ("OPENCODE_GO_API_KEY",):
        status = "set" if os.getenv(env_name) else "not set"
        print(f"[env]     {env_name}: {status}")


def _print_transcription_status(missing: list[str]) -> None:
    try:
        status = validate_transcription_runtime(WhisperTranscriberConfig())
    except TranscriptionRuntimeError as error:
        missing.append("transcription runtime")
        print(f"[missing] transcription runtime: {error}")
        return

    _print_runtime_status("[ok]      transcription runtime", status)


def _print_runtime_status(prefix: str, status) -> None:
    parts = [
        f"{prefix}: {status.backend}",
        f"device={status.device}",
    ]
    if status.compute_type is not None:
        parts.append(f"compute_type={status.compute_type}")
    if status.cuda_device_count:
        parts.append(f"cuda_devices={status.cuda_device_count}")
    if status.supported_compute_types:
        parts.append(f"supported={', '.join(status.supported_compute_types)}")
    if status.binary:
        parts.append(f"binary={status.binary}")
    if status.model:
        parts.append(f"model={status.model}")
    print(" ".join(parts))
