from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import numpy as np

from reframe_agent_host.voice.vad_silero import SileroVoiceActivityDetector
from reframe_agent_host.voice.vad_types import (
    VoiceActivityConfig,
    VoiceActivityDecision,
    VoiceActivityDetector,
)


DetectorFactory = Callable[[VoiceActivityConfig], VoiceActivityDetector]


class TtsBargeInDetector:
    def __init__(
        self,
        config: VoiceActivityConfig,
        *,
        detector_factory: DetectorFactory | None = None,
        required_voice_ms: int = 320,
    ) -> None:
        self._config = replace(config, detector="silero")
        self._detector_factory = detector_factory or SileroVoiceActivityDetector
        self._detector: VoiceActivityDetector | None = None
        self._disabled = False
        self._required_samples = max(
            1,
            int(self._config.sample_rate * required_voice_ms / 1000),
        )
        self._voice_samples = 0
        self._voice_frames: list[np.ndarray] = []
        self._max_voice_samples = max(1, self._config.sample_rate)
        self._triggered = False

    def accept(
        self,
        frame: np.ndarray,
        *,
        tts_active: bool,
        reference_audio: np.ndarray | None = None,
        reference_sample_rate: int | None = None,
    ) -> bool:
        if not tts_active:
            self.reset()
            return False
        if self._disabled:
            return False

        detector = self._get_detector()
        if detector is None:
            return False

        mono_frame = np.asarray(frame, dtype=np.float32).reshape(-1)
        decision = detector.accept(mono_frame)
        if _is_voice(decision):
            if _looks_like_reference_audio(
                mono_frame,
                self._config.sample_rate,
                reference_audio,
                reference_sample_rate,
            ):
                self.reset()
                return False

            self._append_voice_frame(mono_frame)
            if (
                not self._triggered
                and self._voice_samples >= self._required_samples
                and _looks_like_human_speech(
                    np.concatenate(self._voice_frames),
                    self._config.sample_rate,
                )
            ):
                self._triggered = True
                return True
            return False

        if decision.ended or not decision.is_speech:
            self.reset()
        return False

    def reset(self) -> None:
        self._voice_samples = 0
        self._voice_frames = []
        self._triggered = False

    def _append_voice_frame(self, frame: np.ndarray) -> None:
        self._voice_frames.append(frame)
        self._voice_samples += len(frame)
        while self._voice_samples > self._max_voice_samples and self._voice_frames:
            removed = self._voice_frames.pop(0)
            self._voice_samples -= len(removed)

    def _get_detector(self) -> VoiceActivityDetector | None:
        if self._detector is not None:
            return self._detector
        try:
            self._detector = self._detector_factory(self._config)
        except Exception:
            self._disabled = True
            return None
        return self._detector


def _is_voice(decision: VoiceActivityDecision) -> bool:
    return decision.started or decision.is_speech


def _looks_like_human_speech(samples: np.ndarray, sample_rate: int) -> bool:
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    if len(audio) < max(1, int(sample_rate * 0.18)):
        return False

    peak = float(np.max(np.abs(audio)))
    rms = _rms(audio)
    if peak < 0.018 or rms < 0.006:
        return False

    active_ms = _active_ms(audio, sample_rate)
    if active_ms < 180:
        return False

    crest_factor = peak / max(rms, 1e-9)
    if crest_factor > 18:
        return False

    zcr = _zero_crossing_rate(audio)
    if zcr < 0.006 or zcr > 0.42:
        return False

    flatness = _spectral_flatness(audio)
    return flatness < 0.82


def _looks_like_reference_audio(
    frame: np.ndarray,
    frame_sample_rate: int,
    reference_audio: np.ndarray | None,
    reference_sample_rate: int | None,
) -> bool:
    if reference_audio is None or reference_sample_rate is None:
        return False

    mic = np.asarray(frame, dtype=np.float32).reshape(-1)
    reference = np.asarray(reference_audio, dtype=np.float32).reshape(-1)
    if len(mic) < 32 or len(reference) < 32:
        return False
    if _rms(mic) < 0.004 or _rms(reference) < 0.004:
        return False

    reference = _resample(reference, reference_sample_rate, frame_sample_rate)
    if len(reference) < len(mic):
        return False

    reference = reference[-max(len(mic), int(frame_sample_rate * 0.55)) :]
    mic = mic - float(np.mean(mic))
    reference = reference - float(np.mean(reference))

    mic_energy = float(np.dot(mic, mic))
    if mic_energy <= 1e-9:
        return False

    window = np.ones(len(mic), dtype=np.float32)
    dots = np.correlate(reference, mic, mode="valid")
    ref_energy = np.convolve(reference * reference, window, mode="valid")
    valid = ref_energy > 1e-9
    if not np.any(valid):
        return False

    correlations = np.zeros_like(dots)
    correlations[valid] = np.abs(dots[valid]) / np.sqrt(ref_energy[valid] * mic_energy)
    best_index = int(np.argmax(correlations))
    best_correlation = float(correlations[best_index])
    if best_correlation < 0.78:
        return False

    reference_slice = reference[best_index : best_index + len(mic)]
    gain = float(np.dot(mic, reference_slice) / max(np.dot(reference_slice, reference_slice), 1e-9))
    residual = mic - gain * reference_slice
    residual_ratio = _rms(residual) / max(_rms(mic), 1e-9)
    return residual_ratio < 0.55


def _active_ms(samples: np.ndarray, sample_rate: int) -> float:
    frame_samples = max(1, int(sample_rate * 0.032))
    usable = len(samples) - (len(samples) % frame_samples)
    if usable <= 0:
        return 0.0
    frames = samples[:usable].reshape(-1, frame_samples)
    frame_rms = np.sqrt(np.mean(np.square(frames), axis=1, dtype=np.float64))
    return float(np.count_nonzero(frame_rms >= 0.006) * frame_samples * 1000 / sample_rate)


def _zero_crossing_rate(samples: np.ndarray) -> float:
    if len(samples) < 2:
        return 0.0
    centered = samples - float(np.mean(samples))
    signs = np.signbit(centered)
    return float(np.count_nonzero(signs[1:] != signs[:-1]) / (len(samples) - 1))


def _spectral_flatness(samples: np.ndarray) -> float:
    if len(samples) < 8:
        return 1.0
    centered = samples - float(np.mean(samples))
    spectrum = np.abs(np.fft.rfft(centered)) ** 2
    spectrum = spectrum[1:]
    if len(spectrum) == 0:
        return 1.0
    spectrum = np.maximum(spectrum, 1e-12)
    return float(np.exp(np.mean(np.log(spectrum))) / np.mean(spectrum))


def _resample(samples: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return samples.astype(np.float32, copy=False)
    if from_rate <= 0 or to_rate <= 0 or len(samples) == 0:
        return np.empty(0, dtype=np.float32)
    duration = len(samples) / from_rate
    output_count = max(1, int(duration * to_rate))
    source_x = np.linspace(0.0, duration, num=len(samples), endpoint=False)
    target_x = np.linspace(0.0, duration, num=output_count, endpoint=False)
    return np.interp(target_x, source_x, samples).astype(np.float32)


def _rms(samples: np.ndarray) -> float:
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))
