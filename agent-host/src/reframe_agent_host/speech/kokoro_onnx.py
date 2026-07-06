from __future__ import annotations

import os
from pathlib import Path
import time
from urllib.request import urlretrieve

from reframe_agent_host.speech.chunking import speech_chunks
from reframe_agent_host.speech.playback import QueuedAudioOutput
from reframe_agent_host.speech.tts import SpeechEventHandler


MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/kokoro-v1.0.onnx"
)
VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/voices-v1.0.bin"
)
MODEL_FILENAME = "kokoro-v1.0.onnx"
VOICES_FILENAME = "voices-v1.0.bin"


class KokoroOnnxSpeaker:
    def __init__(
        self,
        *,
        voice: str = "af_heart",
        lang: str = "en-us",
        speed: float = 1.0,
    ) -> None:
        self._voice = voice
        self._lang = lang
        self._speed = speed
        self._kokoro = None
        self._output: QueuedAudioOutput | None = None
        self._output_failed = False

    def prepare(self) -> None:
        kokoro = self._get_kokoro()
        kokoro.create(
            "Ready.",
            voice=self._voice,
            speed=self._speed,
            lang=self._lang,
        )
        output = self._audio_output(_sounddevice())
        if output is not None:
            output.clear()

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
        _emit(on_event, "tts-started", f"backend=kokoro-onnx chunks={len(chunks)}")

        sounddevice = _sounddevice()
        output = self._audio_output(sounddevice)
        if output is not None:
            output.clear()
        else:
            sounddevice.stop()

        played_chunks = 0
        for chunk_index, chunk in enumerate(chunks, start=1):
            chunk_started_at = time.perf_counter()
            _emit(
                on_event,
                "tts-chunk-started",
                f"chunk={chunk_index}/{len(chunks)} chars={len(chunk)}",
            )
            samples, sample_rate = self._get_kokoro().create(
                chunk,
                voice=self._voice,
                speed=self._speed,
                lang=self._lang,
            )
            infer_seconds = time.perf_counter() - chunk_started_at
            sample_count = self._play_samples(sounddevice, output, samples, sample_rate)
            played_chunks += 1
            if played_chunks == 1:
                _emit(
                    on_event,
                    "tts-first-audio",
                    f"reply_to_first_audio={time.perf_counter() - started_at:.3f}s",
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

    def _get_kokoro(self):
        if self._kokoro is None:
            from kokoro_onnx import Kokoro

            model_path, voices_path = ensure_kokoro_onnx_assets()
            self._kokoro = Kokoro(str(model_path), str(voices_path))
        return self._kokoro

    def _audio_output(self, sounddevice) -> QueuedAudioOutput | None:
        if self._output_failed:
            return None
        if self._output is None:
            self._output = QueuedAudioOutput(24_000)
        try:
            self._output.start(sounddevice)
        except Exception:
            self._output_failed = True
            self._output = None
            return None
        return self._output

    def _play_samples(self, sounddevice, output, samples, sample_rate: int) -> int:
        if output is not None and sample_rate == 24_000:
            return output.enqueue(samples)
        sounddevice.play(samples, sample_rate)
        sounddevice.wait()
        return len(samples)


def ensure_kokoro_onnx_assets() -> tuple[Path, Path]:
    asset_dir = _asset_dir()
    asset_dir.mkdir(parents=True, exist_ok=True)
    model_path = asset_dir / MODEL_FILENAME
    voices_path = asset_dir / VOICES_FILENAME
    _download_if_missing(MODEL_URL, model_path)
    _download_if_missing(VOICES_URL, voices_path)
    return model_path, voices_path


def _asset_dir() -> Path:
    configured = os.environ.get("REFRAME_KOKORO_ONNX_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "reframe-agent-host" / "kokoro-onnx"


def _download_if_missing(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    urlretrieve(url, tmp_path)
    tmp_path.replace(path)


def _sounddevice():
    import sounddevice

    return sounddevice


def _emit(
    on_event: SpeechEventHandler | None,
    stage: str,
    message: str,
) -> None:
    if on_event is not None:
        on_event(stage, message)
