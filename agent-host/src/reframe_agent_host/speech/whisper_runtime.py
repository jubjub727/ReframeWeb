from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path


GPU_DEVICE = "cuda"
GPU_COMPUTE_TYPES = ("float16", "int8_float16")
DEFAULT_GPU_COMPUTE_TYPE = "float16"
WINDOWS_CUDA_DLLS = ("cublas64_12.dll", "cublasLt64_12.dll")

_DLL_DIRECTORY_HANDLES: list[object] = []


@dataclass(frozen=True)
class WhisperGpuRuntimeStatus:
    cuda_device_count: int
    compute_type: str
    supported_compute_types: tuple[str, ...]


class WhisperGpuRuntimeError(RuntimeError):
    pass


def validate_whisper_gpu_runtime(
    compute_type: str = DEFAULT_GPU_COMPUTE_TYPE,
) -> WhisperGpuRuntimeStatus:
    if compute_type not in GPU_COMPUTE_TYPES:
        raise WhisperGpuRuntimeError(
            "Unsupported GPU compute type "
            f"{compute_type!r}. Use one of: {', '.join(GPU_COMPUTE_TYPES)}."
        )

    _add_cuda_dll_directories()

    import ctranslate2

    cuda_device_count = ctranslate2.get_cuda_device_count()
    if cuda_device_count < 1:
        raise WhisperGpuRuntimeError(
            "No CUDA device was detected by CTranslate2. ReframeWeb voice "
            "transcription is GPU-only."
        )

    supported = tuple(sorted(ctranslate2.get_supported_compute_types(GPU_DEVICE)))
    if compute_type not in supported:
        raise WhisperGpuRuntimeError(
            f"CUDA compute type {compute_type!r} is not supported by this GPU/runtime. "
            f"Supported CUDA compute types: {', '.join(supported)}."
        )

    missing_dlls = _missing_windows_cuda_dlls()
    if missing_dlls:
        raise WhisperGpuRuntimeError(
            "Missing CUDA runtime DLLs required by faster-whisper/CTranslate2: "
            f"{', '.join(missing_dlls)}. Install the CUDA 12 runtime/toolkit so "
            "those DLLs are available, or place them in agent-host\\.cuda\\bin."
        )

    return WhisperGpuRuntimeStatus(
        cuda_device_count=cuda_device_count,
        compute_type=compute_type,
        supported_compute_types=supported,
    )


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
