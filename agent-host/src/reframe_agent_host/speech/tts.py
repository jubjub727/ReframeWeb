from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Lock, Thread
import time
from typing import Protocol


SpeechEventHandler = Callable[[str, str], None]


class TextSpeaker(Protocol):
    def prepare(self) -> None:
        pass

    def interrupt(self, reason: str = "human voice") -> bool:
        pass

    def is_speaking(self) -> bool:
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

    def interrupt(self, reason: str = "human voice") -> bool:
        return False

    def is_speaking(self) -> bool:
        return False

    def speak(
        self,
        text: str,
        *,
        on_event: SpeechEventHandler | None = None,
    ) -> None:
        return None


@dataclass(frozen=True)
class _SpeechJob:
    text: str
    on_event: SpeechEventHandler | None


class QueuedTextSpeaker:
    def __init__(
        self,
        speaker: TextSpeaker,
        *,
        inter_reply_delay_seconds: float = 0.25,
    ) -> None:
        self._speaker = speaker
        self._inter_reply_delay_seconds = inter_reply_delay_seconds
        self._jobs: Queue[_SpeechJob] = Queue()
        self._lock = Lock()
        self._worker: Thread | None = None
        self._active = False

    def prepare(self) -> None:
        self._speaker.prepare()

    def interrupt(self, reason: str = "human voice") -> bool:
        interrupted = self._speaker.interrupt(reason)
        cleared_pending = self._clear_pending()
        return interrupted or cleared_pending

    def is_speaking(self) -> bool:
        with self._lock:
            active = self._active
        return active or not self._jobs.empty() or self._speaker.is_speaking()

    def recent_output_audio(self, seconds: float = 1.0):
        recent_output_audio = getattr(self._speaker, "recent_output_audio", None)
        if recent_output_audio is None:
            return None
        return recent_output_audio(seconds)

    def speak(
        self,
        text: str,
        *,
        on_event: SpeechEventHandler | None = None,
    ) -> None:
        self._ensure_worker()
        self._jobs.put(_SpeechJob(text=text, on_event=on_event))

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is not None:
                return
            self._worker = Thread(target=self._run, daemon=True)
            self._worker.start()

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            with self._lock:
                self._active = True
            try:
                self._speaker.speak(job.text, on_event=job.on_event)
            except Exception as exc:
                _emit(job.on_event, "tts-error", str(exc))
            finally:
                with self._lock:
                    self._active = False
                self._jobs.task_done()
            if self._inter_reply_delay_seconds > 0 and not self._jobs.empty():
                time.sleep(self._inter_reply_delay_seconds)

    def _clear_pending(self) -> bool:
        cleared = False
        while True:
            try:
                self._jobs.get_nowait()
            except Empty:
                return cleared
            cleared = True
            self._jobs.task_done()


def _emit(
    on_event: SpeechEventHandler | None,
    stage: str,
    message: str,
) -> None:
    if on_event is not None:
        on_event(stage, message)
