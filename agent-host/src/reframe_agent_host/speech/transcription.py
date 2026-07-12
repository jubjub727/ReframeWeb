from __future__ import annotations

import numpy as np

from reframe_agent_host.speech.faster_whisper_transcriber import (
    FasterWhisperTranscriber,
)
from reframe_agent_host.speech.transcription_types import (
    CONVERSATION_ON_CONFIRMATION_PROMPT,
    DEFAULT_GPU_COMPUTE_TYPE,
    DEFAULT_TRANSCRIPTION_MAX_GAIN,
    DEFAULT_TRANSCRIPTION_TARGET_RMS,
    DEFAULT_WHISPER_BEAM_SIZE,
    DEFAULT_WHISPER_INITIAL_PROMPT,
    DEFAULT_WHISPER_MODEL,
    GPU_COMPUTE_TYPES,
    GPU_DEVICE,
    Transcript,
    TranscriptSegment,
    Transcriber,
    WhisperTranscriberConfig,
)
from reframe_agent_host.speech.whisper_cpp_transcriber import WhisperCppTranscriber
from reframe_agent_host.speech.whisper_runtime import (
    DEFAULT_BACKEND,
    DEFAULT_CPU_COMPUTE_TYPE,
    DEFAULT_CUDA_COMPUTE_TYPE,
    DEFAULT_CUDA_DEVICE,
    DEFAULT_DEVICE,
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
