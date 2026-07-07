from __future__ import annotations

import ctypes
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


TranscriptionBackend = Literal["auto", "faster-whisper", "whisper-cpp"]
TranscriptionDevice = Literal[
    "auto",
    "cpu",
    "cuda",
    "metal",
    "coreml",
    "vulkan",
    "openvino",
    "rocm",
]

FASTER_WHISPER_DEVICES = ("auto", "cpu", "cuda")
WHISPER_CPP_DEVICES = (
    "auto",
    "cpu",
    "metal",
    "coreml",
    "vulkan",
    "openvino",
    "rocm",
    "cuda",
)
TRANSCRIPTION_BACKENDS: tuple[TranscriptionBackend, ...] = (
    "auto",
    "faster-whisper",
    "whisper-cpp",
)
TRANSCRIPTION_DEVICES: tuple[TranscriptionDevice, ...] = (
    "auto",
    "cpu",
    "cuda",
    "metal",
    "coreml",
    "vulkan",
    "openvino",
    "rocm",
)
TRANSCRIPTION_COMPUTE_TYPES = (
    "auto",
    "default",
    "int8",
    "int8_float32",
    "int8_float16",
    "int16",
    "float16",
    "bfloat16",
    "float32",
)
CUDA_COMPUTE_TYPES = ("float16", "int8_float16")
DEFAULT_BACKEND: TranscriptionBackend = "auto"
DEFAULT_DEVICE: TranscriptionDevice = "auto"
DEFAULT_CUDA_DEVICE = "cuda"
DEFAULT_CUDA_COMPUTE_TYPE = "float16"
DEFAULT_CPU_COMPUTE_TYPE = "int8"
WINDOWS_CUDA_DLLS = ("cublas64_12.dll", "cublasLt64_12.dll")

_DLL_DIRECTORY_HANDLES: list[object] = []


@dataclass(frozen=True)
class TranscriptionRuntimeStatus:
    backend: str
    device: str
    compute_type: str | None
    detail: str
    cuda_device_count: int = 0
    supported_compute_types: tuple[str, ...] = ()
    binary: str | None = None
    model: str | None = None


WhisperGpuRuntimeStatus = TranscriptionRuntimeStatus


class TranscriptionRuntimeError(RuntimeError):
    pass


WhisperGpuRuntimeError = TranscriptionRuntimeError


def validate_transcription_runtime(config) -> TranscriptionRuntimeStatus:
    if config.backend == "whisper-cpp":
        return validate_whisper_cpp_runtime(config)

    if config.backend == "faster-whisper":
        return validate_faster_whisper_runtime(config)

    if config.device in {"metal", "coreml", "vulkan", "openvino", "rocm"}:
        try:
            return validate_whisper_cpp_runtime(config)
        except TranscriptionRuntimeError:
            if not config.allow_cpu_fallback:
                raise

    if config.device == "cpu":
        return validate_faster_whisper_runtime(
            config.with_backend_device("faster-whisper", "cpu")
        )

    cuda_error: TranscriptionRuntimeError | None = None
    if config.device in {"auto", "cuda"}:
        try:
            return validate_faster_whisper_runtime(
                config.with_backend_device("faster-whisper", "cuda")
            )
        except TranscriptionRuntimeError as error:
            cuda_error = error

    try:
        return validate_whisper_cpp_runtime(config)
    except TranscriptionRuntimeError as whisper_cpp_error:
        if config.allow_cpu_fallback:
            return validate_faster_whisper_runtime(
                config.with_backend_device("faster-whisper", "cpu")
            )
        raise cuda_error or whisper_cpp_error


def validate_faster_whisper_runtime(config) -> TranscriptionRuntimeStatus:
    device = _resolved_faster_whisper_device(config)
    compute_type = _resolved_compute_type(config, device)

    if device == "cuda":
        return validate_whisper_gpu_runtime(compute_type)

    import ctranslate2

    supported = _supported_compute_types(ctranslate2, "cpu")
    if compute_type not in {"auto", "default"} and supported and compute_type not in supported:
        raise TranscriptionRuntimeError(
            f"CPU compute type {compute_type!r} is not supported by CTranslate2. "
            f"Supported CPU compute types: {', '.join(supported)}."
        )

    return TranscriptionRuntimeStatus(
        backend="faster-whisper",
        device="cpu",
        compute_type=compute_type,
        detail="faster-whisper CPU runtime ready",
        supported_compute_types=supported,
    )


def validate_whisper_gpu_runtime(
    compute_type: str = DEFAULT_CUDA_COMPUTE_TYPE,
) -> WhisperGpuRuntimeStatus:
    if compute_type not in CUDA_COMPUTE_TYPES:
        raise TranscriptionRuntimeError(
            "Unsupported CUDA compute type "
            f"{compute_type!r}. Use one of: {', '.join(CUDA_COMPUTE_TYPES)}."
        )

    _add_cuda_dll_directories()

    import ctranslate2

    cuda_device_count = ctranslate2.get_cuda_device_count()
    if cuda_device_count < 1:
        raise TranscriptionRuntimeError(
            "No CUDA device was detected by CTranslate2."
        )

    supported = _supported_compute_types(ctranslate2, DEFAULT_CUDA_DEVICE)
    if compute_type not in supported:
        raise TranscriptionRuntimeError(
            f"CUDA compute type {compute_type!r} is not supported by this GPU/runtime. "
            f"Supported CUDA compute types: {', '.join(supported)}."
        )

    missing_dlls = _missing_windows_cuda_dlls()
    if missing_dlls:
        raise TranscriptionRuntimeError(
            "Missing CUDA runtime DLLs required by faster-whisper/CTranslate2: "
            f"{', '.join(missing_dlls)}. Install the CUDA 12 runtime/toolkit so "
            "those DLLs are available, or place them in agent-host\\.cuda\\bin."
        )

    return TranscriptionRuntimeStatus(
        backend="faster-whisper",
        device="cuda",
        compute_type=compute_type,
        detail="faster-whisper CUDA runtime ready",
        cuda_device_count=cuda_device_count,
        supported_compute_types=supported,
    )


def validate_whisper_cpp_runtime(config) -> TranscriptionRuntimeStatus:
    binary = resolve_whisper_cpp_binary(config.whisper_cpp_bin)
    if binary is None:
        raise TranscriptionRuntimeError(
            "whisper.cpp was selected but no whisper-cli binary was found. "
            "Set --whisper-cpp-bin or put whisper-cli on PATH."
        )

    model = resolve_whisper_cpp_model(config)
    if model is None:
        raise TranscriptionRuntimeError(
            "whisper.cpp was selected but no ggml model file was found. "
            "Set --whisper-cpp-model, or pass a local .bin model path with "
            "--whisper-model."
        )

    return TranscriptionRuntimeStatus(
        backend="whisper-cpp",
        device=config.device,
        compute_type=None,
        detail="whisper.cpp runtime ready",
        binary=str(binary),
        model=str(model),
    )


def resolve_whisper_cpp_binary(configured: str | None) -> Path | None:
    candidates: list[str] = []
    if configured:
        candidates.append(configured)
    candidates.extend(
        [
            "whisper-cli",
            "whisper-cli.exe",
            "main",
            "main.exe",
        ]
    )

    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file():
            return path.resolve()
        found = shutil.which(candidate)
        if found:
            return Path(found).resolve()
    return None


def resolve_whisper_cpp_model(config) -> Path | None:
    for value in (config.whisper_cpp_model, config.model_size_or_path):
        if not value:
            continue
        path = Path(value).expanduser()
        if path.is_file() and path.suffix.lower() == ".bin":
            return path.resolve()
    return None


def _resolved_faster_whisper_device(config) -> str:
    if config.device in {"metal", "coreml", "vulkan", "openvino", "rocm"}:
        raise TranscriptionRuntimeError(
            f"faster-whisper does not support {config.device!r}. "
            "Use the whisper.cpp backend for non-CUDA GPU acceleration."
        )
    if config.device == "cpu":
        return "cpu"
    if config.device == "cuda":
        return "cuda"

    try:
        import ctranslate2
    except ImportError:
        raise TranscriptionRuntimeError("faster-whisper requires CTranslate2.")

    try:
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass

    if config.allow_cpu_fallback:
        return "cpu"
    raise TranscriptionRuntimeError("No CUDA device detected and CPU fallback is disabled.")


def _resolved_compute_type(config, device: str) -> str:
    if device == "cuda":
        if config.compute_type in {"auto", "default", "int8", "int8_float32", "float32"}:
            return DEFAULT_CUDA_COMPUTE_TYPE
        return config.compute_type

    if config.compute_type in {"auto", "default", "float16", "int8_float16"}:
        return config.cpu_compute_type
    return config.compute_type


def _supported_compute_types(ctranslate2, device: str) -> tuple[str, ...]:
    try:
        return tuple(sorted(ctranslate2.get_supported_compute_types(device)))
    except Exception:
        return ()


def _missing_windows_cuda_dlls() -> list[str]:
    if sys.platform != "win32":
        return []

    missing: list[str] = []
    for dll_name in WINDOWS_CUDA_DLLS:
        try:
            ctypes.CDLL(dll_name)
        except OSError:
            missing.append(dll_name)

    return missing


def _add_cuda_dll_directories() -> None:
    if sys.platform != "win32":
        return

    for directory in _candidate_cuda_dll_directories():
        if not directory.is_dir():
            continue

        try:
            handle = os.add_dll_directory(str(directory))
        except (FileNotFoundError, OSError):
            continue

        _DLL_DIRECTORY_HANDLES.append(handle)


def _candidate_cuda_dll_directories() -> list[Path]:
    directories = _environment_cuda_directories()

    project_root = Path(__file__).resolve().parents[2]
    directories.insert(0, project_root / ".cuda" / "bin")

    for import_path in sys.path:
        site_path = Path(import_path)
        directories.append(site_path / "nvidia" / "cublas" / "bin")
        directories.append(site_path / "nvidia" / "cuda_runtime" / "bin")
        directories.append(site_path / "nvidia" / "cudnn" / "bin")

    toolkit_root = Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA")
    if toolkit_root.is_dir():
        directories.extend(sorted(toolkit_root.glob("v*/bin"), reverse=True))

    return _dedupe_directories(directories)


def _environment_cuda_directories() -> list[Path]:
    directories: list[Path] = []

    cuda_path = os.environ.get("CUDA_PATH")
    if cuda_path:
        directories.append(Path(cuda_path) / "bin")

    for name, value in os.environ.items():
        if name.startswith("CUDA_PATH_V") and value:
            directories.append(Path(value) / "bin")

    return directories


def _dedupe_directories(directories: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for directory in directories:
        key = str(directory).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(directory)
    return unique
