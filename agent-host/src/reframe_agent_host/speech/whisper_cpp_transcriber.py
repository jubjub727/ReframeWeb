from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import tempfile
from threading import RLock
import wave

import numpy as np

from reframe_agent_host.speech.transcription_types import (
    Transcript,
    TranscriptSegment,
    WhisperTranscriberConfig,
)
from reframe_agent_host.speech.whisper_runtime import (
    TranscriptionRuntimeError,
    resolve_whisper_cpp_binary,
    resolve_whisper_cpp_model,
    validate_transcription_runtime,
)
from reframe_agent_host.voice.input_level import normalize_active_level


class WhisperCppTranscriber:
    def __init__(self, config: WhisperTranscriberConfig) -> None:
        self._config = config
        self._binary: Path | None = None
        self._model: Path | None = None
        self._lock = RLock()

    @property
    def label(self) -> str:
        device = self._config.device
        return f"whisper.cpp/{device}" if device != "auto" else "whisper.cpp"

    def prepare(self) -> None:
        with self._lock:
            self._binary = resolve_whisper_cpp_binary(self._config.whisper_cpp_bin)
            self._model = resolve_whisper_cpp_model(self._config)
            if self._binary is None or self._model is None:
                validate_transcription_runtime(
                    self._config.with_backend_device(
                        "whisper-cpp", self._config.device
                    )
                )

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> Transcript:
        return self.transcribe_with_prompt(
            samples, sample_rate, self._config.initial_prompt
        )

    def transcribe_with_prompt(
        self,
        samples: np.ndarray,
        sample_rate: int,
        initial_prompt: str | None,
    ) -> Transcript:
        if sample_rate != 16_000:
            raise ValueError("whisper.cpp transcription expects 16000 Hz audio.")
        audio = _normalized_audio(samples, sample_rate, self._config)
        with self._lock:
            self.prepare()
            assert self._binary is not None and self._model is not None
            return self._run_cli(audio, sample_rate, initial_prompt)

    def _run_cli(
        self,
        audio: np.ndarray,
        sample_rate: int,
        initial_prompt: str | None,
    ) -> Transcript:
        assert self._binary is not None and self._model is not None
        with tempfile.TemporaryDirectory(prefix="reframe-whisper-cpp-") as directory:
            work_dir = Path(directory)
            wav_path = work_dir / "utterance.wav"
            output_stem = work_dir / "transcript"
            _write_wav(wav_path, audio, sample_rate)
            try:
                completed = subprocess.run(
                    self._command(wav_path, output_stem, initial_prompt),
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError as error:
                raise TranscriptionRuntimeError(
                    f"Could not run whisper.cpp binary {self._binary}: {error}"
                ) from error
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()
                raise TranscriptionRuntimeError(
                    "whisper.cpp transcription failed"
                    + (f": {detail}" if detail else ".")
                )
            json_path = output_stem.with_suffix(".json")
            if json_path.exists():
                return transcript_from_whisper_cpp_json(
                    json.loads(json_path.read_text(encoding="utf-8")),
                    sample_rate=sample_rate,
                    sample_count=len(audio),
                    fallback_language=self._config.language,
                )
            return _transcript_from_text(
                _clean_stdout(completed.stdout),
                sample_rate,
                len(audio),
                self._config.language,
            )

    def _command(
        self,
        wav_path: Path,
        output_stem: Path,
        initial_prompt: str | None = None,
    ) -> list[str]:
        command = [
            str(self._binary),
            "-m",
            str(self._model),
            "-f",
            str(wav_path),
            "-oj",
            "-of",
            str(output_stem),
        ]
        if self._config.language:
            command.extend(["-l", self._config.language])
        if initial_prompt:
            command.extend(["--prompt", initial_prompt])
        if self._config.device == "openvino":
            command.extend(["--ov-e-device", "GPU"])
        command.extend(self._config.whisper_cpp_extra_args)
        return command


def transcript_from_whisper_cpp_json(
    payload: object,
    *,
    sample_rate: int,
    sample_count: int,
    fallback_language: str | None,
) -> Transcript:
    if not isinstance(payload, dict):
        return _transcript_from_text(
            "", sample_rate, sample_count, fallback_language
        )
    raw_segments = payload.get("transcription")
    segments = []
    if isinstance(raw_segments, list):
        for item in raw_segments:
            if isinstance(item, dict):
                start, end = _segment_times(item)
                segments.append(
                    TranscriptSegment(
                        start=start,
                        end=end,
                        text=str(item.get("text", "")).strip(),
                    )
                )
    result = payload.get("result")
    language = (
        result.get("language")
        if isinstance(result, dict) and isinstance(result.get("language"), str)
        else fallback_language
    )
    return Transcript(
        text=" ".join(item.text for item in segments).strip(),
        language=language,
        duration_seconds=sample_count / sample_rate,
        segments=segments,
    )


def _normalized_audio(samples, sample_rate, config):
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    if config.normalize_audio:
        return normalize_active_level(
            audio,
            sample_rate=sample_rate,
            target_active_rms=config.normalization_target_rms,
            max_gain=config.normalization_max_gain,
            limiter_ceiling=config.normalization_limiter_ceiling,
        )
    return np.clip(audio, -1.0, 1.0)


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def _segment_times(item: dict[str, object]) -> tuple[float, float]:
    offsets = item.get("offsets")
    if isinstance(offsets, dict):
        start, end = _offset_seconds(offsets.get("from")), _offset_seconds(offsets.get("to"))
        if start is not None and end is not None:
            return start, end
    timestamps = item.get("timestamps")
    if isinstance(timestamps, dict):
        start = _timestamp_seconds(timestamps.get("from"))
        end = _timestamp_seconds(timestamps.get("to"))
        if start is not None and end is not None:
            return start, end
    return 0.0, 0.0


def _offset_seconds(value: object) -> float | None:
    return float(value) / 1000.0 if isinstance(value, int | float) else None


def _timestamp_seconds(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d+):(\d+):(\d+)(?:[,.](\d+))?\s*", value)
    if match is None:
        return None
    hours, minutes, seconds, fraction = match.groups()
    total = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    return float(total) + (float("0." + fraction) if fraction else 0.0)


def _transcript_from_text(text, sample_rate, sample_count, language):
    clean = " ".join(text.split())
    segment = TranscriptSegment(0.0, sample_count / sample_rate, clean)
    return Transcript(
        clean,
        language,
        sample_count / sample_rate,
        [segment] if clean else [],
    )


def _clean_stdout(stdout: str) -> str:
    lines = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("whisper_", "system_info:", "main:")):
            lines.append(re.sub(r"^\[[^\]]+\]\s*", "", stripped))
    return " ".join(lines).strip()
