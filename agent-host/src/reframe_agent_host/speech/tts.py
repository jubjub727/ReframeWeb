from __future__ import annotations

from contextlib import contextmanager, redirect_stderr
import io
import os
from typing import Protocol
import warnings


class TextSpeaker(Protocol):
    def prepare(self) -> None:
        pass

    def speak(self, text: str) -> None:
        pass


class NoopSpeaker:
    def prepare(self) -> None:
        return None

    def speak(self, text: str) -> None:
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

    def prepare(self) -> None:
        with _quiet_dependency_output():
            pipeline = self._get_pipeline()
            pipeline.load_voice(self._voice)

    def speak(self, text: str) -> None:
        clean = " ".join(text.split())
        if not clean:
            return

        sounddevice = _sounddevice()
        sounddevice.stop()
        with _quiet_dependency_output():
            for result in self._get_pipeline()(clean, voice=self._voice):
                audio = result.audio
                if audio is None:
                    continue
                samples = audio.detach().cpu().numpy()
                sounddevice.play(samples, self._sample_rate)
                sounddevice.wait()

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
