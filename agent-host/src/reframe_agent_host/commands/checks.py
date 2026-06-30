from __future__ import annotations

import importlib
import os
import sys

from reframe_agent_host import __version__
from reframe_agent_host.voice.audio_devices import list_input_devices
from reframe_agent_host.speech.transcription import (
    WhisperGpuRuntimeError,
    validate_whisper_gpu_runtime,
)


DEPENDENCY_IMPORTS: tuple[tuple[str, str], ...] = (
    ("baml-py", "baml_py"),
    ("numpy", "numpy"),
    ("sounddevice", "sounddevice"),
    ("pocketsphinx", "pocketsphinx"),
    ("silero-vad", "silero_vad"),
    ("faster-whisper", "faster_whisper"),
    ("kokoro", "kokoro"),
)


def run_doctor() -> int:
    missing: list[str] = []
    print(f"reframe-agent-host {__version__}")
    _print_dependency_status(missing)
    _print_environment_status()
    _print_gpu_status(missing)
    return 1 if missing else 0


def run_gpu_check(compute_type: str) -> int:
    try:
        status = validate_whisper_gpu_runtime(compute_type)
    except WhisperGpuRuntimeError as error:
        print(f"[missing] CUDA faster-whisper runtime: {error}", file=sys.stderr)
        return 1

    print("CUDA faster-whisper runtime ready")
    print(f"devices: {status.cuda_device_count}")
    print(f"compute_type: {status.compute_type}")
    print(f"supported_compute_types: {', '.join(status.supported_compute_types)}")
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


def _print_gpu_status(missing: list[str]) -> None:
    try:
        status = validate_whisper_gpu_runtime()
    except WhisperGpuRuntimeError as error:
        missing.append("CUDA faster-whisper runtime")
        print(f"[missing] CUDA faster-whisper runtime: {error}")
        return

    print(
        "[ok]      CUDA faster-whisper runtime: "
        f"{status.cuda_device_count} device(s), "
        f"{status.compute_type}, "
        f"supported={', '.join(status.supported_compute_types)}"
    )
