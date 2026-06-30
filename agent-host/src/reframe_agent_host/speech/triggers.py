from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


TriggerKind = Literal["wake_command", "conversation_on"]

CONFIRMED_PREFIX_ALIASES: dict[str, tuple[str, ...]] = {
    "jarvis": ("travis",),
    "conversation on": (
        "conversation one",
        "conservation on",
        "conservation one",
    ),
}


@dataclass(frozen=True)
class TriggerPhraseConfig:
    trigger_words: tuple[str, ...] = ("jarvis",)
    conversation_on_phrases: tuple[str, ...] = ("conversation on",)


@dataclass(frozen=True)
class TriggerPhraseDetection:
    kind: TriggerKind
    phrase: str
    routed_transcript: str


class TriggerPhraseMatcher:
    def __init__(self, config: TriggerPhraseConfig) -> None:
        self._trigger_patterns = tuple(
            ("wake_command", *_compile_prefix_pattern(word))
            for word in config.trigger_words
        ) + tuple(
            ("conversation_on", *_compile_prefix_pattern(phrase))
            for phrase in config.conversation_on_phrases
        )

    def match(self, transcript: str) -> TriggerPhraseDetection | None:
        for kind, phrase, pattern in self._trigger_patterns:
            match = pattern.match(transcript)
            if match:
                return TriggerPhraseDetection(
                    kind=kind,
                    phrase=phrase,
                    routed_transcript=_clean_remainder(match.group("remainder")),
                )

        return None

    def match_confirmed(
        self,
        transcript: str,
        kind: TriggerKind,
        phrase: str,
    ) -> TriggerPhraseDetection | None:
        for candidate in _confirmed_prefixes(phrase):
            matched_phrase, pattern = _compile_prefix_pattern(candidate)
            match = pattern.match(transcript)
            if match:
                return TriggerPhraseDetection(
                    kind=kind,
                    phrase=matched_phrase,
                    routed_transcript=_clean_remainder(match.group("remainder")),
                )
        return None


def _compile_prefix_pattern(phrase: str) -> tuple[str, re.Pattern[str]]:
    normalized = " ".join(phrase.lower().split())
    if not normalized:
        raise ValueError("Trigger phrases cannot be empty.")

    escaped_words = [re.escape(word) for word in normalized.split()]
    phrase_pattern = r"[\s,.;:!?-]+".join(escaped_words)
    pattern = re.compile(
        rf"^\s*[\W_]*(?P<trigger>{phrase_pattern})\b"
        rf"(?P<remainder>[\s,.;:!?-]*(?:.*))$",
        re.IGNORECASE,
    )
    return normalized, pattern


def _confirmed_prefixes(phrase: str) -> tuple[str, ...]:
    normalized = " ".join(phrase.lower().split())
    return (normalized, *CONFIRMED_PREFIX_ALIASES.get(normalized, ()))


def _clean_remainder(value: str) -> str:
    return value.strip(" \t\r\n,.;:!?-")
