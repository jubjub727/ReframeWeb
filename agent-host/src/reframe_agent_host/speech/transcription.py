from __future__ import annotations

import json
import re
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Protocol

import numpy as np

from reframe_agent_host.speech.whisper_runtime import (
    DEFAULT_BACKEND,
    DEFAULT_CPU_COMPUTE_TYPE,
    DEFAULT_CUDA_COMPUTE_TYPE,
    DEFAULT_DEVICE,
    DEFAULT_CUDA_DEVICE,
    TRANSCRIPTION_BACKENDS,
    TRANSCRIPTION_COMPUTE_TYPES,
    TRANSCRIPTION_DEVICES,
    TranscriptionRuntimeError,
    TranscriptionRuntimeStatus,
    WhisperGpuRuntimeError,
    WhisperGpuRuntimeStatus,
    resolve_whisper_cpp_binary,
    resolve_whisper_cpp_model,
    validate_faster_whisper_runtime,
    validate_transcription_runtime,
    validate_whisper_gpu_runtime,
)
from reframe_agent_host.voice.input_level import normalize_active_level


DEFAULT_WHISPER_MODEL = "large-v3"
DEFAULT_WHISPER_BEAM_SIZE = 5
DEFAULT_TRANSCRIPTION_TARGET_RMS = 0.1
DEFAULT_TRANSCRIPTION_MAX_GAIN = 5.0
DEFAULT_WHISPER_INITIAL_PROMPT = (
    "The speaker uses a New Zealand English accent. Wake-command prompts often "
    "start with the wake word Jarvis. At the start of a prompt, words like "
    "just, Java, or Travis may be misheard forms of Jarvis. Requests may mention "
    "jokes."
)
CONVERSATION_ON_CONFIRMATION_PROMPT = (
    "This is a short control-phrase confirmation clip. The speaker may use a "
    "New Zealand English accent. Listen for whether they clearly said "
    "'conversation on'. It may sound like 'conversation one', 'conservation on', "
    "or 'conservation one'. If that phrase is not clearly present, transcribe "
    "the actual words you hear without inventing the control phrase."
)
DEFAULT_GPU_COMPUTE_TYPE = DEFAULT_CUDA_COMPUTE_TYPE
GPU_COMPUTE_TYPES = ("float16", "int8_float16")
GPU_DEVICE = DEFAULT_CUDA_DEVICE


class Transcriber(Protocol):
    @property
    def label(self) -> str:
        pass

    def prepare(self) -> None:
        pass

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> "Transcript":
        pass


@dataclass(frozen=True)
class WhisperTranscriberConfig:
    model_size_or_path: str = DEFAULT_WHISPER_MODEL
    backend: str = DEFAULT_BACKEND
    device: str = DEFAULT_DEVICE
    compute_type: str = "auto"
    cpu_compute_type: str = DEFAULT_CPU_COMPUTE_TYPE
    allow_cpu_fallback: bool = True
    whisper_cpp_bin: str | None = None
    whisper_cpp_model: str | None = None
    whisper_cpp_extra_args: tuple[str, ...] = ()
    language: str | None = "en"
    beam_size: int = DEFAULT_WHISPER_BEAM_SIZE
    normalize_audio: bool = True
    normalization_target_rms: float = DEFAULT_TRANSCRIPTION_TARGET_RMS
    normalization_max_gain: float = DEFAULT_TRANSCRIPTION_MAX_GAIN
    normalization_limiter_ceiling: float = 0.95
    initial_prompt: str | None = DEFAULT_WHISPER_INITIAL_PROMPT

    def with_backend_device(self, backend: str, device: str) -> "WhisperTranscriberConfig":
        return WhisperTranscriberConfig(
            model_size_or_path=self.model_size_or_path,
            backend=backend,
            device=device,
            compute_type=self.compute_type,
            cpu_compute_type=self.cpu_compute_type,
            allow_cpu_fallback=self.allow_cpu_fallback,
            whisper_cpp_bin=self.whisper_cpp_bin,
            whisper_cpp_model=self.whisper_cpp_model,
            whisper_cpp_extra_args=self.whisper_cpp_extra_args,
            language=self.language,
            beam_size=self.beam_size,
            normalize_audio=self.normalize_audio,
            normalization_target_rms=self.normalization_target_rms,
            normalization_max_gain=self.normalization_max_gain,
            normalization_limiter_ceiling=self.normalization_limiter_ceiling,
            initial_prompt=self.initial_prompt,
        )


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None
    duration_seconds: float
    segments: list[TranscriptSegment]

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "language": self.language,
            "duration_seconds": self.duration_seconds,
            "segments": [
                {"start": segment.start, "end": segment.end, "text": segment.text}
                for segment in self.segments
            ],
        }


def create_transcriber(config: WhisperTranscriberConfig) -> Transcriber:
    status = validate_transcription_runtime(config)
    if status.backend == "whisper-cpp":
        return WhisperCppTranscriber(config)
    return FasterWhisperTranscriber(
        config.with_backend_device("faster-whisper", status.device)
    )


def transcribe_with_initial_prompt(
    transcriber: Transcriber,
    samples: np.ndarray,
    sample_rate: int,
    initial_prompt: str,
) -> Transcript:
    transcribe_with_prompt = getattr(transcriber, "transcribe_with_prompt", None)
    if transcribe_with_prompt is None:
        return transcriber.transcribe(samples, sample_rate)
    return transcribe_with_prompt(samples, sample_rate, initial_prompt)


class FasterWhisperTranscriber:
    def __init__(self, config: WhisperTranscriberConfig) -> None:
        self._config = config
        self._model = None
        self._lock = RLock()
        self._status: TranscriptionRuntimeStatus | None = None

    @property
    def label(self) -> str:
        if self._status is not None:
            return f"faster-whisper/{self._status.device}"
        return "faster-whisper"

    def prepare(self) -> None:
        with self._lock:
            self._load_model()

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> Transcript:
        return self.transcribe_with_prompt(
            samples,
            sample_rate,
            self._config.initial_prompt,
        )

    def transcribe_with_prompt(
        self,
        samples: np.ndarray,
        sample_rate: int,
        initial_prompt: str | None,
    ) -> Transcript:
        if sample_rate != 16_000:
            raise ValueError("faster-whisper ndarray transcription expects 16000 Hz audio.")

        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        if self._config.normalize_audio:
            audio = normalize_active_level(
                audio,
                sample_rate=sample_rate,
                target_active_rms=self._config.normalization_target_rms,
                max_gain=self._config.normalization_max_gain,
                limiter_ceiling=self._config.normalization_limiter_ceiling,
            )
        else:
            audio = np.clip(audio, -1.0, 1.0)

        with self._lock:
            model = self._load_model()
            segments_iter, info = model.transcribe(
                audio,
                language=self._config.language,
                beam_size=self._config.beam_size,
                condition_on_previous_text=False,
                initial_prompt=initial_prompt,
            )
            segments = [
                TranscriptSegment(
                    start=float(segment.start),
                    end=float(segment.end),
                    text=segment.text.strip(),
                )
                for segment in segments_iter
            ]
            language = getattr(info, "language", None)
            duration_seconds = float(
                getattr(info, "duration", len(audio) / sample_rate)
            )
        text = " ".join(segment.text for segment in segments).strip()

        return Transcript(
            text=text,
            language=language,
            duration_seconds=duration_seconds,
            segments=segments,
        )

    def _load_model(self):
        if self._model is not None:
            return self._model

        self._status = validate_faster_whisper_runtime(self._config)

        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            self._config.model_size_or_path,
            device=self._status.device,
            compute_type=self._status.compute_type,
        )
        return self._model


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
                    self._config.with_backend_device("whisper-cpp", self._config.device)
                )

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> Transcript:
        if sample_rate != 16_000:
            raise ValueError("whisper.cpp transcription expects 16000 Hz audio.")

        audio = _normalized_audio(samples, sample_rate, self._config)
        with self._lock:
            self.prepare()
            assert self._binary is not None
            assert self._model is not None
            return self._run_cli(audio, sample_rate, initial_prompt=None)

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
            assert self._binary is not None
            assert self._model is not None
            return self._run_cli(audio, sample_rate, initial_prompt=initial_prompt)

    def _run_cli(
        self,
        audio: np.ndarray,
        sample_rate: int,
        initial_prompt: str | None,
    ) -> Transcript:
        assert self._binary is not None
        assert self._model is not None

        with tempfile.TemporaryDirectory(prefix="reframe-whisper-cpp-") as directory:
            work_dir = Path(directory)
            wav_path = work_dir / "utterance.wav"
            output_stem = work_dir / "transcript"
            _write_wav(wav_path, audio, sample_rate)
            command = self._command(wav_path, output_stem, initial_prompt)
            try:
                completed = subprocess.run(
                    command,
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
                return _transcript_from_whisper_cpp_json(
                    json.loads(json_path.read_text(encoding="utf-8")),
                    sample_rate=sample_rate,
                    sample_count=len(audio),
                    fallback_language=self._config.language,
                )

            return _transcript_from_text(
                _clean_whisper_cpp_stdout(completed.stdout),
                sample_rate=sample_rate,
                sample_count=len(audio),
                language=self._config.language,
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


def _normalized_audio(
    samples: np.ndarray,
    sample_rate: int,
    config: WhisperTranscriberConfig,
) -> np.ndarray:
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


def _transcript_from_whisper_cpp_json(
    payload: object,
    *,
    sample_rate: int,
    sample_count: int,
    fallback_language: str | None,
) -> Transcript:
    if not isinstance(payload, dict):
        return _transcript_from_text("", sample_rate, sample_count, fallback_language)

    raw_segments = payload.get("transcription")
    segments: list[TranscriptSegment] = []
    if isinstance(raw_segments, list):
        for item in raw_segments:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            start, end = _segment_times(item)
            segments.append(TranscriptSegment(start=start, end=end, text=text))

    text = " ".join(segment.text for segment in segments).strip()
    language = fallback_language
    result = payload.get("result")
    if isinstance(result, dict) and isinstance(result.get("language"), str):
        language = result["language"]

    return Transcript(
        text=text,
        language=language,
        duration_seconds=sample_count / sample_rate,
        segments=segments,
    )


def _segment_times(item: dict[str, object]) -> tuple[float, float]:
    offsets = item.get("offsets")
    if isinstance(offsets, dict):
        start = _offset_seconds(offsets.get("from"))
        end = _offset_seconds(offsets.get("to"))
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
    if isinstance(value, (int, float)):
        return float(value) / 1000.0
    return None


def _timestamp_seconds(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d+):(\d+):(\d+)(?:[,.](\d+))?\s*", value)
    if match is None:
        return None
    hours, minutes, seconds, fraction = match.groups()
    total = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    if fraction:
        total += float("0." + fraction)
    return float(total)


def _transcript_from_text(
    text: str,
    sample_rate: int,
    sample_count: int,
    language: str | None,
) -> Transcript:
    clean = " ".join(text.split())
    segment = TranscriptSegment(
        start=0.0,
        end=sample_count / sample_rate,
        text=clean,
    )
    return Transcript(
        text=clean,
        language=language,
        duration_seconds=sample_count / sample_rate,
        segments=[segment] if clean else [],
    )


def _clean_whisper_cpp_stdout(stdout: str) -> str:
    lines = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("whisper_", "system_info:", "main:")):
            continue
        lines.append(re.sub(r"^\[[^\]]+\]\s*", "", stripped))
    return " ".join(lines).strip()
