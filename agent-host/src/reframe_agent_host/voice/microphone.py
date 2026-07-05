from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event
import time
from typing import Iterator

import numpy as np

from reframe_agent_host.voice.audio_devices import (
    device_default_sample_rate,
    device_input_channels,
    device_summary,
    list_input_devices,
    resolve_input_device,
)
from reframe_agent_host.voice.resampling import AudioFrameProcessor


@dataclass(frozen=True)
class AudioInputConfig:
    sample_rate: int = 16_000
    input_sample_rate: int | None = None
    input_gain: float = 1.0
    limiter_ceiling: float = 0.95
    chunk_ms: int = 32
    channels: int = 0
    channel: int = 0
    device: int | str | None = None
    queue_seconds: float = 12.0
    start_retries: int = 5
    start_retry_delay_seconds: float = 0.2

    @property
    def chunk_samples(self) -> int:
        return max(1, int(self.sample_rate * self.chunk_ms / 1000))

    @property
    def queue_chunks(self) -> int:
        return max(2, int(self.queue_seconds * 1000 / self.chunk_ms))


class MicrophoneStream:
    def __init__(self, config: AudioInputConfig) -> None:
        self._config = config
        self._queue: Queue[np.ndarray] = Queue(maxsize=config.queue_chunks)
        self._stop_event = Event()
        self._stream = None
        self._dropped_frames = 0
        self._last_status: str | None = None
        self._resolved_device: int | str | None = None
        self._input_sample_rate = config.sample_rate
        self._input_channels = 1
        self._processor: AudioFrameProcessor | None = None

    @property
    def dropped_frames(self) -> int:
        return self._dropped_frames

    @property
    def last_status(self) -> str | None:
        return self._last_status

    @property
    def input_sample_rate(self) -> int:
        return self._input_sample_rate

    @property
    def input_channels(self) -> int:
        return self._input_channels

    @property
    def device_summary(self) -> str:
        return device_summary(self._resolved_device)

    def __enter__(self) -> MicrophoneStream:
        import sounddevice as sd

        self._resolved_device = resolve_input_device(self._config.device)
        self._input_sample_rate = (
            self._config.input_sample_rate
            or device_default_sample_rate(self._resolved_device)
        )
        self._input_channels = self._config.channels or min(
            2,
            max(1, device_input_channels(self._resolved_device)),
        )
        self._processor = AudioFrameProcessor(
            source_rate=self._input_sample_rate,
            target_rate=self._config.sample_rate,
            chunk_samples=self._config.chunk_samples,
            gain=self._config.input_gain,
            limiter_ceiling=self._config.limiter_ceiling,
        )
        stream_chunk_samples = max(
            1,
            int(round(self._input_sample_rate * self._config.chunk_ms / 1000)),
        )

        def callback(indata, _frames, _time_info, status) -> None:
            if status:
                self._last_status = str(status)

            mono = self._to_mono(indata)
            assert self._processor is not None

            for frame in self._processor.accept(mono):
                try:
                    self._queue.put_nowait(frame)
                except Full:
                    self._dropped_frames += 1

        self._stream = self._open_started_stream(
            sd,
            {
                "samplerate": self._input_sample_rate,
                "blocksize": stream_chunk_samples,
                "channels": self._input_channels,
                "dtype": "float32",
                "device": self._resolved_device,
                "callback": callback,
            },
        )
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()

    def close(self) -> None:
        self._stop_event.set()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def frames(
        self,
        timeout_seconds: float = 0.25,
        stop_event: Event | None = None,
    ) -> Iterator[np.ndarray]:
        while not self._stop_event.is_set() and not _stopped(stop_event):
            try:
                yield self._queue.get(timeout=timeout_seconds)
            except Empty:
                continue

    def _to_mono(self, indata) -> np.ndarray:
        mono = np.asarray(indata, dtype=np.float32)
        if mono.ndim == 2:
            channel = min(max(0, self._config.channel), mono.shape[1] - 1)
            return mono[:, channel]
        return mono.reshape(-1)

    def _open_started_stream(self, sounddevice, stream_kwargs):
        attempts = max(1, self._config.start_retries + 1)
        for attempt in range(attempts):
            stream = None
            try:
                stream = sounddevice.InputStream(**stream_kwargs)
                stream.start()
                return stream
            except Exception:
                if stream is not None:
                    with suppress(Exception):
                        stream.close()
                if attempt == attempts - 1:
                    raise
                time.sleep(self._config.start_retry_delay_seconds * (attempt + 1))
        raise RuntimeError("unreachable microphone startup retry state")


def _stopped(stop_event: Event | None) -> bool:
    return stop_event is not None and stop_event.is_set()
