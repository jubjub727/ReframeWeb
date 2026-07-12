from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys


WINDOWS_CUDA_DLLS = ("cublas64_12.dll", "cublasLt64_12.dll")
_DLL_DIRECTORY_HANDLES: list[object] = []


def add_cuda_dll_directories() -> None:
    if sys.platform != "win32":
        return
    for directory in candidate_cuda_dll_directories():
        if not directory.is_dir():
            continue
        try:
            handle = os.add_dll_directory(str(directory))
        except (FileNotFoundError, OSError):
            continue
        _DLL_DIRECTORY_HANDLES.append(handle)


def missing_windows_cuda_dlls() -> list[str]:
    if sys.platform != "win32":
        return []
    missing = []
    for dll_name in WINDOWS_CUDA_DLLS:
        try:
            ctypes.CDLL(dll_name)
        except OSError:
            missing.append(dll_name)
    return missing


def candidate_cuda_dll_directories() -> list[Path]:
    directories = _environment_cuda_directories()
    project_root = Path(__file__).resolve().parents[2]
    directories.insert(0, project_root / ".cuda" / "bin")
    for import_path in sys.path:
        site_path = Path(import_path)
        directories.extend(
            (
                site_path / "nvidia" / "cublas" / "bin",
                site_path / "nvidia" / "cuda_runtime" / "bin",
                site_path / "nvidia" / "cudnn" / "bin",
            )
        )
    toolkit_root = Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA")
    if toolkit_root.is_dir():
        directories.extend(sorted(toolkit_root.glob("v*/bin"), reverse=True))
    return _dedupe_directories(directories)


def _environment_cuda_directories() -> list[Path]:
    directories = []
    if cuda_path := os.environ.get("CUDA_PATH"):
        directories.append(Path(cuda_path) / "bin")
    directories.extend(
        Path(value) / "bin"
        for name, value in os.environ.items()
        if name.startswith("CUDA_PATH_V") and value
    )
    return directories


def _dedupe_directories(directories: list[Path]) -> list[Path]:
    seen = set()
    unique = []
    for directory in directories:
        key = str(directory).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(directory)
    return unique
