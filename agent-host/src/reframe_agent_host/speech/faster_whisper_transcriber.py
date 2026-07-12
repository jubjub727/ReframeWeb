from __future__ import annotations

from threading import RLock

import numpy as np

from reframe_agent_host.speech.transcription_types import (
    Transcript,
    TranscriptSegment,
    WhisperTranscriberConfig,
)
from reframe_agent_host.speech.whisper_runtime import (
    TranscriptionRuntimeStatus,
    validate_faster_whisper_runtime,
)
from reframe_agent_host.voice.input_level import normalize_active_level


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
            samples, sample_rate, self._config.initial_prompt
        )

    def transcribe_with_prompt(
        self,
        samples: np.ndarray,
        sample_rate: int,
        initial_prompt: str | None,
    ) -> Transcript:
        if sample_rate != 16_000:
            raise ValueError(
                "faster-whisper ndarray transcription expects 16000 Hz audio."
            )
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
                    start=float(item.start),
                    end=float(item.end),
                    text=item.text.strip(),
                )
                for item in segments_iter
            ]
            language = getattr(info, "language", None)
            duration = float(getattr(info, "duration", len(audio) / sample_rate))
        return Transcript(
            text=" ".join(item.text for item in segments).strip(),
            language=language,
            duration_seconds=duration,
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
