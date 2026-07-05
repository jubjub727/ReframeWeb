from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from reframe_agent_host.voice.audio_quality import AudioQualityReport


DEFAULT_AUDIO_CALIBRATION_FILE = ".reframe-audio-calibration.json"


@dataclass(frozen=True)
class AudioCalibration:
    input_gain: float
    device: str | None = None


def recommend_input_gain(
    report: AudioQualityReport,
    *,
    target_peak: float = 0.35,
    target_active_rms: float = 0.065,
    max_gain: float = 8.0,
) -> float:
    metrics = report.metrics
    candidates = []
    if metrics.peak > 0:
        candidates.append(target_peak / metrics.peak)
    if metrics.active_rms > 0:
        candidates.append(target_active_rms / metrics.active_rms)
    if not candidates:
        return max_gain

    gain = max(candidates)
    gain = max(1.0, min(max_gain, gain))
    return round(gain, 2)


def load_audio_calibration(path: str | Path) -> AudioCalibration | None:
    calibration_path = Path(path)
    if not calibration_path.is_file():
        return None

    payload = json.loads(calibration_path.read_text(encoding="utf-8"))
    input_gain = float(payload.get("input_gain", 1.0))
    return AudioCalibration(
        input_gain=max(0.0, input_gain),
        device=payload.get("device"),
    )


def save_audio_calibration(
    path: str | Path,
    *,
    input_gain: float,
    report: AudioQualityReport,
    recording: dict[str, object],
) -> Path:
    calibration_path = Path(path)
    calibration_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_gain": input_gain,
        "device": recording.get("device"),
        "source_quality": report.to_dict(),
        "recording": recording,
    }
    calibration_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return calibration_path
