from __future__ import annotations

import json
import re
import wave
from collections import deque
from datetime import datetime
from pathlib import Path
import time

import numpy as np


class DebugAudioRecorder:
    def __init__(
        self,
        directory: str | None,
        sample_rate: int,
        max_seconds: float,
        period_seconds: float = 0.0,
    ) -> None:
        self._directory = Path(directory) if directory else None
        self._sample_rate = sample_rate
        self._period_seconds = period_seconds
        self._last_periodic_save_at = time.monotonic()
        self._frames: deque[float] = deque(
            maxlen=max(1, int(max_seconds * sample_rate))
        )

    @property
    def enabled(self) -> bool:
        return self._directory is not None

    def append(self, frame: np.ndarray) -> None:
        if not self.enabled:
            return
        samples = np.asarray(frame, dtype=np.float32).reshape(-1)
        self._frames.extend(float(sample) for sample in samples)

    def save(self, label: str, metadata: dict[str, object] | None = None) -> Path | None:
        if not self.enabled or not self._frames:
            return None

        directory = self._directory
        assert directory is not None
        directory.mkdir(parents=True, exist_ok=True)

        samples = np.asarray(self._frames, dtype=np.float32)
        stem = f"{_timestamp()}-{_slug(label)}"
        wav_path = directory / f"{stem}.wav"
        _write_wav(wav_path, samples, self._sample_rate)
        _write_metadata(
            wav_path.with_suffix(".json"),
            label,
            samples,
            self._sample_rate,
            metadata,
        )
        return wav_path

    def save_and_emit(
        self,
        label: str,
        on_event,
        metadata: dict[str, object] | None = None,
    ) -> None:
        path = self.save(label, metadata=metadata)
        if path is not None and on_event is not None:
            on_event("debug-audio", str(path))

    def maybe_save_periodic(self, on_event) -> None:
        if not self.enabled or self._period_seconds <= 0:
            return
        now = time.monotonic()
        if now - self._last_periodic_save_at < self._period_seconds:
            return
        self._last_periodic_save_at = now
        self.save_and_emit("periodic", on_event, {"period_seconds": self._period_seconds})


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def _write_metadata(
    path: Path,
    label: str,
    samples: np.ndarray,
    sample_rate: int,
    metadata: dict[str, object] | None,
) -> None:
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    rms = float(np.sqrt(np.mean(np.square(samples)))) if len(samples) else 0.0
    payload = {
        "label": label,
        "sample_rate": sample_rate,
        "duration_seconds": len(samples) / sample_rate,
        "peak": peak,
        "rms": rms,
        "metadata": metadata or {},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "audio"
