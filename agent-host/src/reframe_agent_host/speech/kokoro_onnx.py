from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from threading import Lock
import time
from urllib.request import urlretrieve

import numpy as np

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
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[’'\-][A-Za-z0-9]+)*")


@dataclass(frozen=True)
class _PlaybackChunk:
    text: str
    char_start: int
    sample_start: int
    sample_end: int


@dataclass
class _PlaybackState:
    text: str
    on_event: SpeechEventHandler | None
    chunks: list[_PlaybackChunk] = field(default_factory=list)
    output: QueuedAudioOutput | None = None
    playback_started_at: float | None = None
    playback_sample_rate: int = 24_000
    interrupted: bool = False


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
        self._playback_lock = Lock()
        self._playback: _PlaybackState | None = None

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

        state = self._begin_playback(clean, on_event)
        started_at = time.perf_counter()
        try:
            chunks = speech_chunks(clean)
            chunk_spans = _chunk_spans(clean, chunks)
            _emit(on_event, "tts-started", f"backend=kokoro-onnx chunks={len(chunks)}")

            sounddevice = _sounddevice()
            output = self._audio_output(sounddevice)
            if output is not None:
                output.clear(reset_played_samples=True)
                self._set_output(state, output)
            else:
                sounddevice.stop()
                self._set_output(state, None)

            played_chunks = 0
            queued_samples = 0
            for chunk_index, chunk in enumerate(chunks, start=1):
                if self._interrupted(state):
                    return
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
                if self._interrupted(state):
                    return
                infer_seconds = time.perf_counter() - chunk_started_at
                sample_count = _sample_count(samples)
                self._add_playback_chunk(
                    state,
                    _PlaybackChunk(
                        text=chunk,
                        char_start=chunk_spans[chunk_index - 1],
                        sample_start=queued_samples,
                        sample_end=queued_samples + sample_count,
                    ),
                )
                self._mark_playback_started(state, sample_rate)
                sample_count = self._play_samples(
                    sounddevice,
                    output,
                    samples,
                    sample_rate,
                )
                queued_samples += sample_count
                played_chunks += 1
                if played_chunks == 1:
                    _emit(
                        on_event,
                        "tts-first-audio",
                        (
                            "reply_to_first_audio="
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
            if self._interrupted(state):
                return
            _emit(
                on_event,
                "tts-finished",
                f"chunks={played_chunks} total={time.perf_counter() - started_at:.3f}s",
            )
        finally:
            self._finish_playback(state)

    def interrupt(self, reason: str = "human voice") -> bool:
        with self._playback_lock:
            state = self._playback
            if state is None or state.interrupted:
                return False
            state.interrupted = True
            detail = self._interruption_detail_locked(state)

        if self._output is not None:
            self._output.clear()
        try:
            _sounddevice().stop()
        except Exception:
            pass
        _emit(state.on_event, "tts-interrupted", detail)
        return True

    def is_speaking(self) -> bool:
        with self._playback_lock:
            return self._playback is not None and not self._playback.interrupted

    def recent_output_audio(self, seconds: float = 1.0) -> tuple[np.ndarray, int]:
        if self._output is None:
            return np.empty(0, dtype=np.float32), 24_000
        return self._output.recent_samples(seconds), self._output.sample_rate

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

    def _begin_playback(
        self,
        text: str,
        on_event: SpeechEventHandler | None,
    ) -> _PlaybackState:
        state = _PlaybackState(text=text, on_event=on_event)
        with self._playback_lock:
            self._playback = state
        return state

    def _finish_playback(self, state: _PlaybackState) -> None:
        with self._playback_lock:
            if self._playback is state:
                self._playback = None

    def _interrupted(self, state: _PlaybackState) -> bool:
        with self._playback_lock:
            return state.interrupted

    def _set_output(
        self,
        state: _PlaybackState,
        output: QueuedAudioOutput | None,
    ) -> None:
        with self._playback_lock:
            if self._playback is state:
                state.output = output

    def _add_playback_chunk(
        self,
        state: _PlaybackState,
        chunk: _PlaybackChunk,
    ) -> None:
        with self._playback_lock:
            if self._playback is state:
                state.chunks.append(chunk)

    def _mark_playback_started(
        self,
        state: _PlaybackState,
        sample_rate: int,
    ) -> None:
        with self._playback_lock:
            if self._playback is not state:
                return
            if state.playback_started_at is None:
                state.playback_started_at = time.perf_counter()
                state.playback_sample_rate = sample_rate

    def _interruption_detail_locked(self, state: _PlaybackState) -> str:
        played_samples = 0
        if state.playback_started_at is not None:
            elapsed = max(0.0, time.perf_counter() - state.playback_started_at)
            played_samples = int(elapsed * state.playback_sample_rate)
        if state.output is not None:
            played_samples = min(played_samples, state.output.played_samples)
        return _last_spoken_word_detail(state.text, state.chunks, played_samples)


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


def _chunk_spans(text: str, chunks: tuple[str, ...]) -> list[int]:
    spans = []
    cursor = 0
    for chunk in chunks:
        index = text.find(chunk, cursor)
        if index < 0:
            index = cursor
        spans.append(index)
        cursor = index + len(chunk)
    return spans


def _sample_count(samples) -> int:
    return len(np.asarray(samples, dtype=np.float32).reshape(-1))


def _last_spoken_word_detail(
    text: str,
    chunks: list[_PlaybackChunk],
    played_samples: int,
) -> str:
    word = "<none>"
    character_index = 0

    for chunk in chunks:
        if played_samples <= chunk.sample_start:
            break
        if chunk.sample_end <= chunk.sample_start:
            continue

        if played_samples >= chunk.sample_end:
            char_limit = len(chunk.text)
        else:
            ratio = (played_samples - chunk.sample_start) / (
                chunk.sample_end - chunk.sample_start
            )
            char_limit = max(0, min(len(chunk.text), int(len(chunk.text) * ratio)))

        for match in _WORD_RE.finditer(chunk.text):
            if match.end() <= char_limit:
                word = match.group(0)
                character_index = chunk.char_start + match.end()
            else:
                break

    if not text:
        character_index = 0
    return f"Last fully spoken word {word} at character {character_index}"
