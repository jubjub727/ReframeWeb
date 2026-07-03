from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from reframe_agent_host.voice.microphone import AudioInputConfig, MicrophoneStream


DEFAULT_CASES = (
    "negative-hello:hello hello",
    "negative-command:do this",
    "trailing-wake:do this jarvis",
    "prefixed-wake:this is a test jarvis do this",
    "wake-command:jarvis do this",
    "conversation-on:conversation on",
)


def run_record_wake_audio(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_config = _audio_config(args)
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "seconds": args.seconds,
        "audio": {
            "device": args.device,
            "sample_rate": args.sample_rate,
            "input_sample_rate": args.input_sample_rate,
            "input_gain": args.input_gain,
            "chunk_ms": args.chunk_ms,
            "input_channels": args.input_channels,
            "input_channel": args.input_channel,
        },
        "clips": [],
    }

    cases = args.case or list(DEFAULT_CASES)
    for index, case in enumerate(cases, start=1):
        label, prompt = _parse_case(case)
        print(
            f"[case {index}/{len(cases)}] {label}: say {prompt!r}",
            file=sys.stderr,
        )
        if not args.no_prompt:
            input("Press Enter when you are ready to record...")
        _countdown(args.countdown_seconds)

        samples, metadata = _record_samples(audio_config, args.seconds)
        wav_path = output_dir / f"{_timestamp()}-{_slug(label)}.wav"
        _write_wav(wav_path, samples, args.sample_rate)
        clip = {
            "label": label,
            "prompt": prompt,
            "wav": str(wav_path),
            "recording": metadata,
        }
        manifest["clips"].append(clip)
        _write_json(wav_path.with_suffix(".json"), clip)
        print(f"[saved] {wav_path}", file=sys.stderr)

    manifest_path = output_dir / f"{_timestamp()}-manifest.json"
    _write_json(manifest_path, manifest)
    print(json.dumps(manifest, indent=2))
    print(f"[wake-record] manifest={manifest_path}", file=sys.stderr)
    return 0


def _audio_config(args: argparse.Namespace) -> AudioInputConfig:
    return AudioInputConfig(
        sample_rate=args.sample_rate,
        input_sample_rate=args.input_sample_rate or None,
        input_gain=args.input_gain,
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
                    "dropped_frames": microphone.dropped_frames,
                    "last_status": microphone.last_status,
                }
                break
    print("[recording] stop", file=sys.stderr)
    samples = np.concatenate(frames)[:target_samples]
    return samples, metadata


def _parse_case(value: str) -> tuple[str, str]:
    if ":" not in value:
        return _slug(value), value
    label, prompt = value.split(":", 1)
    return _slug(label), prompt.strip()


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


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _coerce_device(value: str | None) -> int | str | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def _slug(value: str) -> str:
    return (
        "".join(char if char.isalnum() else "-" for char in value.lower()).strip("-")
        or "audio"
    )
