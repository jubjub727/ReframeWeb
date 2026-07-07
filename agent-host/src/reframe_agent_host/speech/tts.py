from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


SpeechEventHandler = Callable[[str, str], None]


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
