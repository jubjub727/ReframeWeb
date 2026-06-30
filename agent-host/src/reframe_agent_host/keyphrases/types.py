from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


KeyphraseKind = Literal[
    "wake_command",
    "conversation_on",
]


@dataclass(frozen=True)
class KeyphraseSpotterConfig:
    trigger_words: tuple[str, ...] = ("jarvis",)
    conversation_on_phrases: tuple[str, ...] = ("conversation on",)
    conversation_on_confirm_window_ms: int = 2_000
    check_interval_ms: int = 320
    carry_ms: int = 2_000
    gain: float = 1.0


@dataclass(frozen=True)
class KeyphraseDetection:
    kind: KeyphraseKind
    phrase: str
    hypstr: str
    confirmed: bool
    phrase_end_sample: int | None = None


@dataclass(frozen=True)
class PhraseMatch:
    phrase: str
    matched_phrase: str
    kind: KeyphraseKind
