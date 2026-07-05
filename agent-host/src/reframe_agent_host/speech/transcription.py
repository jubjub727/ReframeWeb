from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

import numpy as np

from reframe_agent_host.speech.whisper_runtime import (
    DEFAULT_GPU_COMPUTE_TYPE,
    GPU_COMPUTE_TYPES,
    GPU_DEVICE,
    WhisperGpuRuntimeError,
    WhisperGpuRuntimeStatus,
    validate_whisper_gpu_runtime,
)


@dataclass(frozen=True)
class WhisperTranscriberConfig:
    model_size_or_path: str = "base.en"
    compute_type: str = DEFAULT_GPU_COMPUTE_TYPE
    language: str | None = "en"
    beam_size: int = 1


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


class FasterWhisperTranscriber:
    def __init__(self, config: WhisperTranscriberConfig) -> None:
        self._config = config
        self._model = None
        self._lock = RLock()

    def prepare(self) -> None:
        with self._lock:
            self._load_model()

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> Transcript:
        if sample_rate != 16_000:
            raise ValueError("faster-whisper ndarray transcription expects 16000 Hz audio.")

        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        audio = np.clip(audio, -1.0, 1.0)

        with self._lock:
            model = self._load_model()
            segments_iter, info = model.transcribe(
                audio,
                language=self._config.language,
                beam_size=self._config.beam_size,
                condition_on_previous_text=False,
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

        validate_whisper_gpu_runtime(self._config.compute_type)

        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            self._config.model_size_or_path,
            device=GPU_DEVICE,
            compute_type=self._config.compute_type,
        )
        return self._model
