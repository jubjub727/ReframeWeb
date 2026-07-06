from __future__ import annotations

from contextlib import contextmanager, redirect_stderr
import io
import os
import time
from collections.abc import Callable
from typing import Protocol
import warnings

from reframe_agent_host.speech.chunking import speech_chunks
from reframe_agent_host.speech.playback import QueuedAudioOutput


SpeechEventHandler = Callable[[str, str], None]
_WARMUP_TEXT = "Ready."


class TextSpeaker(Protocol):
    def prepare(self) -> None:
        pass

    def speak(
        self,
        text: str,
        *,
        on_event: SpeechEventHandler | None = None,
    ) -> None:
        pass


class NoopSpeaker:
    def prepare(self) -> None:
        return None

    def speak(
        self,
        text: str,
        *,
        on_event: SpeechEventHandler | None = None,
    ) -> None:
        return None


class KokoroSpeaker:
    def __init__(
        self,
        *,
        voice: str = "af_heart",
        lang_code: str = "a",
        sample_rate: int = 24000,
        device: str | None = None,
    ) -> None:
        self._voice = voice
        self._lang_code = lang_code
        self._sample_rate = sample_rate
        self._device = device
        self._pipeline = None
        self._output: QueuedAudioOutput | None = None
        self._output_failed = False

    def prepare(self) -> None:
        with _quiet_dependency_output(), _torch_inference_mode():
            pipeline = self._get_pipeline()
            pipeline.load_voice(self._voice)
            self._warm_model(pipeline)
        self._prepare_audio_output()

    def speak(
        self,
        text: str,
        *,
        on_event: SpeechEventHandler | None = None,
    ) -> None:
        clean = " ".join(text.split())
        if not clean:
            return

        started_at = time.perf_counter()
        chunks = speech_chunks(clean)
        _emit(
            on_event,
            "tts-started",
            f"chars={len(clean)} chunks={len(chunks)}",
        )

        sounddevice = _sounddevice()
        output = self._audio_output(sounddevice)
        if output is not None:
            output.clear()
        else:
            sounddevice.stop()
        played_chunks = 0
        with _quiet_dependency_output(), _torch_inference_mode():
            pipeline = self._get_pipeline()
            for chunk_index, chunk in enumerate(chunks, start=1):
                chunk_started_at = time.perf_counter()
                _emit(
                    on_event,
                    "tts-chunk-started",
                    f"chunk={chunk_index}/{len(chunks)} chars={len(chunk)}",
                )
                samples = self._synthesize_chunk(pipeline, chunk)
                if samples is None:
                    continue

                infer_seconds = time.perf_counter() - chunk_started_at
                sample_count = self._play_samples(sounddevice, output, samples)
                played_chunks += 1

                if played_chunks == 1:
                    _emit(
                        on_event,
                        "tts-first-audio",
                        (
                            f"reply_to_first_audio="
                            f"{time.perf_counter() - started_at:.3f}s"
                        ),
                    )
                _emit(
                    on_event,
                    "tts-play-started",
                    (
                        f"chunk={chunk_index}/{len(chunks)} "
                        f"samples={sample_count} infer={infer_seconds:.3f}s"
                    ),
                )
            if output is not None:
                output.wait_until_drained()
        _emit(
            on_event,
            "tts-finished",
            f"chunks={played_chunks} total={time.perf_counter() - started_at:.3f}s",
        )

    def _get_pipeline(self):
        if self._pipeline is None:
            _configure_hf_token_aliases()
            from kokoro import KPipeline

            self._pipeline = KPipeline(
                lang_code=self._lang_code,
                repo_id="hexgrad/Kokoro-82M",
                device=self._device,
            )
        return self._pipeline

    def _synthesize_chunk(self, pipeline, chunk: str):
        for result in pipeline(chunk, voice=self._voice, split_pattern=None):
            audio = result.audio
            if audio is not None:
                return audio.detach().cpu().numpy()
        return None

    def _prepare_audio_output(self) -> None:
        sounddevice = _sounddevice()
        output = self._audio_output(sounddevice)
        if output is None:
            return
        output.clear()

    def _audio_output(self, sounddevice) -> QueuedAudioOutput | None:
        if self._output_failed:
            return None
        if self._output is None:
            self._output = QueuedAudioOutput(self._sample_rate)
        try:
            self._output.start(sounddevice)
        except Exception:
            self._output_failed = True
            self._output = None
            return None
        return self._output

    def _play_samples(self, sounddevice, output, samples) -> int:
        if output is not None:
            return output.enqueue(samples)
        sounddevice.play(samples, self._sample_rate)
        sounddevice.wait()
        return len(samples)

    def _warm_model(self, pipeline) -> None:
        for result in pipeline(_WARMUP_TEXT, voice=self._voice, split_pattern=None):
            audio = result.audio
            if audio is not None:
                _ = audio.shape
                return


def _sounddevice():
    import sounddevice

    return sounddevice


def _configure_hf_token_aliases() -> None:
    token = (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
    )
    if not token:
        return
    os.environ.setdefault("HF_TOKEN", token)
    os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", token)


def _emit(
    on_event: SpeechEventHandler | None,
    stage: str,
    message: str,
) -> None:
    if on_event is not None:
        on_event(stage, message)


@contextmanager
def _quiet_dependency_output():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="dropout option adds dropout.*",
            category=UserWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message=".*torch.nn.utils.weight_norm.*",
            category=FutureWarning,
        )
        with redirect_stderr(io.StringIO()):
            yield


@contextmanager
def _torch_inference_mode():
    try:
        import torch
    except ImportError:
        yield
        return

    with torch.inference_mode():
        yield
