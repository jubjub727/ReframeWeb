from __future__ import annotations

import os
from pathlib import Path
from urllib.request import urlretrieve


MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/kokoro-v1.0.onnx"
)
VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/voices-v1.0.bin"
)
MODEL_FILENAME = "kokoro-v1.0.onnx"
VOICES_FILENAME = "voices-v1.0.bin"


def ensure_kokoro_onnx_assets() -> tuple[Path, Path]:
    asset_dir = _asset_dir()
    asset_dir.mkdir(parents=True, exist_ok=True)
    model_path = asset_dir / MODEL_FILENAME
    voices_path = asset_dir / VOICES_FILENAME
    _download_if_missing(MODEL_URL, model_path)
    _download_if_missing(VOICES_URL, voices_path)
    return model_path, voices_path


def _asset_dir() -> Path:
    configured = os.environ.get("REFRAME_KOKORO_ONNX_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "reframe-agent-host" / "kokoro-onnx"


def _download_if_missing(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    if temporary_path.exists():
        temporary_path.unlink()
    urlretrieve(url, temporary_path)
    temporary_path.replace(path)
