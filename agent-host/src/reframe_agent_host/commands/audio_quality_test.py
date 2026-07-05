from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from reframe_agent_host.voice.audio_calibration import (
    load_audio_calibration,
    recommend_input_gain,
    save_audio_calibration,
)
from reframe_agent_host.voice.audio_quality import analyze_audio_quality
from reframe_agent_host.voice.microphone import AudioInputConfig, MicrophoneStream


def run_audio_quality_test(args: argparse.Namespace) -> int:
    audio_config = _audio_config(args)
    if not args.no_prompt:
        print(f"Say: {args.prompt!r}", file=sys.stderr)
        input("Press Enter when you are ready to record...")
    _countdown(args.countdown_seconds)

    samples, recording = _record_samples(audio_config, args.seconds)
    report = analyze_audio_quality(samples, args.sample_rate)
    recommended_gain = round(
        audio_config.input_gain * recommend_input_gain(report),
        2,
    )
    calibration_path = None
    calibration_error = None
    if args.save_calibration and _can_save_calibration(report):
        calibration_path = save_audio_calibration(
            args.calibration_file,
            input_gain=recommended_gain,
            report=report,
            recording=recording,
        )
    elif args.save_calibration:
        calibration_error = "calibration needs captured, unclipped speech"
    wav_path = _save_recording(
        args.output_dir,
        samples,
        args.sample_rate,
        report,
        recording,
        recommended_gain,
    )

    _print_report(
        report,
        wav_path,
        recording,
        recommended_gain,
        calibration_path,
        calibration_error,
    )
    return 0 if report.ok or calibration_path is not None else 1


def _audio_config(args: argparse.Namespace) -> AudioInputConfig:
    input_gain = args.input_gain
    if args.use_calibration:
        calibration = load_audio_calibration(args.calibration_file)
        input_gain = calibration.input_gain if calibration is not None else input_gain

    return AudioInputConfig(
        sample_rate=args.sample_rate,
        input_sample_rate=args.input_sample_rate or None,
        input_gain=input_gain,
        limiter_ceiling=args.limiter_ceiling,
        chunk_ms=args.chunk_ms,
        channels=args.input_channels,
        channel=args.input_channel,
        device=_coerce_device(args.device),
    )


def _record_samples(
    config: AudioInputConfig,
    seconds: float,
) -> tuple[np.ndarray, dict[str, object]]:
    target_samples = max(1, int(config.sample_rate * seconds))
    frames: list[np.ndarray] = []
    captured_samples = 0
    print("[recording] start", file=sys.stderr)
    with MicrophoneStream(config) as microphone:
        for frame in microphone.frames():
            frames.append(frame)
            captured_samples += len(frame)
            if captured_samples >= target_samples:
                metadata = {
                    "device": microphone.device_summary,
                    "input_sample_rate": microphone.input_sample_rate,
                    "input_channels": microphone.input_channels,
                    "selected_channel": config.channel,
                    "input_gain": config.input_gain,
                    "limiter_ceiling": config.limiter_ceiling,
                    "dropped_frames": microphone.dropped_frames,
                    "last_status": microphone.last_status,
                }
                break
    print("[recording] stop", file=sys.stderr)
    return np.concatenate(frames)[:target_samples], metadata


def _save_recording(
    output_dir: str,
    samples: np.ndarray,
    sample_rate: int,
    report,
    recording: dict[str, object],
    recommended_gain: float,
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    wav_path = directory / f"{_timestamp()}-audio-quality.wav"
    _write_wav(wav_path, samples, sample_rate)
    payload = {
        "recording": recording,
        "quality": report.to_dict(),
        "recommended_input_gain": recommended_gain,
        "wav": str(wav_path),
    }
    wav_path.with_suffix(".json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return wav_path


def _print_report(
    report,
    wav_path: Path,
    recording: dict[str, object],
    recommended_gain: float,
    calibration_path: Path | None,
    calibration_error: str | None,
) -> None:
    metrics = report.metrics
    print(f"audio_quality: {'ok' if report.ok else 'bad'}")
    print(f"wav: {wav_path}")
    print(f"device: {recording['device']}")
    print(
        "levels: "
        f"peak={metrics.peak:.3f} "
        f"rms={metrics.rms:.3f} "
        f"active_rms={metrics.active_rms:.3f} "
        f"active={metrics.active_fraction:.0%} "
        f"clipped={metrics.clipped_fraction:.2%}"
    )
    print(f"recommended_input_gain: {recommended_gain:g}")
    if calibration_path is not None:
        print(f"saved_calibration: {calibration_path}")
    if calibration_error is not None:
        print(f"calibration_error: {calibration_error}")
    for problem in report.problems:
        print(f"problem: {problem}")


def _can_save_calibration(report) -> bool:
    blockers = {"not enough speech was captured", "audio is clipping"}
    return not blockers.intersection(report.problems)


def _countdown(seconds: float) -> None:
    if seconds <= 0:
        return
    print(f"[recording] starts in {seconds:g}s", file=sys.stderr)
    time.sleep(seconds)


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def _coerce_device(value: str | None) -> int | str | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")
