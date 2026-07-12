from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

import numpy as np

from reframe_agent_host.speech.whisper_runtime import (
    DEFAULT_BACKEND,
    DEFAULT_CPU_COMPUTE_TYPE,
    DEFAULT_CUDA_COMPUTE_TYPE,
    DEFAULT_CUDA_DEVICE,
    DEFAULT_DEVICE,
)


DEFAULT_WHISPER_MODEL = "large-v3"
DEFAULT_WHISPER_BEAM_SIZE = 5
DEFAULT_TRANSCRIPTION_TARGET_RMS = 0.1
DEFAULT_TRANSCRIPTION_MAX_GAIN = 5.0
DEFAULT_WHISPER_INITIAL_PROMPT = (
    "The speaker may use a New Zealand English accent. This is a spoken prompt in "
    "a natural conversation with a voice assistant. Transcribe it as ordinary "
    "conversational English, using the grammar and meaning of the complete prompt "
    "to resolve ambiguous speech. Wake-command prompts often start with the wake "
    "word Jarvis. At the start of a prompt, words like just, Java, or Travis may "
    "be misheard forms of Jarvis."
)
CONVERSATION_ON_CONFIRMATION_PROMPT = (
    "The speaker may use a New Zealand English accent. This is a short spoken "
    "response in a natural conversation with a voice assistant. 'Conversation "
    "on' is a possible control phrase. Transcribe it as ordinary conversational "
    "English, using the grammar and meaning of the complete utterance. Do not add "
    "words unsupported by the audio."
)
DEFAULT_GPU_COMPUTE_TYPE = DEFAULT_CUDA_COMPUTE_TYPE
GPU_COMPUTE_TYPES = ("float16", "int8_float16")
GPU_DEVICE = DEFAULT_CUDA_DEVICE


class Transcriber(Protocol):
    @property
    def label(self) -> str: ...

    def prepare(self) -> None: ...

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> Transcript: ...


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

    def with_backend_device(
        self,
        backend: str,
        device: str,
    ) -> WhisperTranscriberConfig:
        return replace(self, backend=backend, device=device)


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
                {"start": item.start, "end": item.end, "text": item.text}
                for item in self.segments
            ],
        }
