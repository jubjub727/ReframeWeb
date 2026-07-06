from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


TriggerKind = Literal["wake_command", "conversation_on"]

TRIGGER_PREFIX_ALIASES: dict[str, tuple[str, ...]] = {
    "jarvis": (
        "java",
        "java's",
        "javas",
        "javis",
        "jarivs",
        "jar vice",
        "jar vis",
        "jar viss",
        "jarvice",
        "jarviss",
        "jarvis's",
        "jarvus",
        "jervis",
        "jervus",
        "jervais",
        "charvis",
        "garvis",
        "travis",
    ),
    "conversation on": (
        "conversation one",
        "conservation on",
        "conservation one",
    ),
}

CONFIRMED_WAKE_RESIDUES: dict[str, tuple[str, ...]] = {
    "jarvis": ("just",),
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
            ("wake_command", phrase, pattern)
            for word in config.trigger_words
            for phrase, pattern in _compile_prefix_patterns(word)
        ) + tuple(
            ("conversation_on", phrase, pattern)
            for phrase in config.conversation_on_phrases
            for phrase, pattern in _compile_prefix_patterns(phrase)
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
        normalized = _normalize_phrase(phrase)
        for candidate in _prefix_candidates(normalized):
            pattern = _compile_prefix_pattern(candidate)
            match = pattern.match(transcript)
            if match:
                return TriggerPhraseDetection(
                    kind=kind,
                    phrase=normalized,
                    routed_transcript=_clean_remainder(match.group("remainder")),
                )
        if kind == "wake_command":
            for residue in CONFIRMED_WAKE_RESIDUES.get(normalized, ()):
                pattern = _compile_prefix_pattern(residue)
                match = pattern.match(transcript)
                if match:
                    return TriggerPhraseDetection(
                        kind=kind,
                        phrase=normalized,
                        routed_transcript=_clean_remainder(match.group("remainder")),
                    )
        return None


def _compile_prefix_patterns(phrase: str) -> tuple[tuple[str, re.Pattern[str]], ...]:
    normalized = _normalize_phrase(phrase)
    return tuple(
        (normalized, _compile_prefix_pattern(candidate))
        for candidate in _prefix_candidates(normalized)
    )


def _compile_prefix_pattern(phrase: str) -> re.Pattern[str]:
    normalized = _normalize_phrase(phrase)
    if not normalized:
        raise ValueError("Trigger phrases cannot be empty.")

    escaped_words = [re.escape(word) for word in normalized.split()]
    phrase_pattern = r"[\s,.;:!?-]+".join(escaped_words)
    pattern = re.compile(
        rf"^\s*[\W_]*(?P<trigger>{phrase_pattern})\b"
        rf"(?P<remainder>[\s,.;:!?-]*(?:.*))$",
        re.IGNORECASE,
    )
    return pattern


def _prefix_candidates(normalized_phrase: str) -> tuple[str, ...]:
    return (normalized_phrase, *TRIGGER_PREFIX_ALIASES.get(normalized_phrase, ()))


def _normalize_phrase(phrase: str) -> str:
    return " ".join(phrase.lower().split())


def _clean_remainder(value: str) -> str:
    return value.strip(" \t\r\n,.;:!?-")
