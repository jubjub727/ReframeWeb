from __future__ import annotations

import re


DEFAULT_MAX_SPEECH_CHUNK_CHARS = 180
DEFAULT_FIRST_SPEECH_CHUNK_CHARS = 96


def speech_chunks(
    text: str,
    max_chars: int = DEFAULT_MAX_SPEECH_CHUNK_CHARS,
    first_chunk_chars: int = DEFAULT_FIRST_SPEECH_CHUNK_CHARS,
) -> tuple[str, ...]:
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    if first_chunk_chars < 1:
        raise ValueError("first_chunk_chars must be at least 1")

    clean = " ".join(text.split())
    if not clean:
        return ()

    first, remaining = _first_fragment(clean, first_chunk_chars)
    chunks: list[str] = []
    if first:
        chunks.append(first)

    current = ""
    for sentence in re.split(r"(?<=[.!?;:])\s+", remaining):
        for piece in _split_long_fragment(sentence, max_chars):
            if not current:
                current = piece
            elif len(current) + 1 + len(piece) <= max_chars:
                current = f"{current} {piece}"
            else:
                chunks.append(current)
                current = piece
    if current:
        chunks.append(current)
    return tuple(chunks)


def _first_fragment(text: str, max_chars: int) -> tuple[str, str]:
    if len(text) <= max_chars:
        return text, ""

    split_at = _first_split_index(text, max_chars)
    return text[:split_at].strip(), text[split_at:].strip()


def _first_split_index(text: str, max_chars: int) -> int:
    window = text[: max_chars + 1]
    lower_bound = max(12, max_chars // 3)

    for match in re.finditer(r"[.!?;:,]\s+", window):
        if lower_bound <= match.end() <= max_chars:
            return match.end()

    for separator in (
        " and ",
        " but ",
        " so ",
        " then ",
        " because ",
        " while ",
        " which ",
        " that ",
    ):
        index = window.rfind(separator)
        if index >= lower_bound:
            return index

    index = window.rfind(" ")
    if index >= lower_bound:
        return index
    return max_chars


def _split_long_fragment(fragment: str, max_chars: int) -> tuple[str, ...]:
    remaining = fragment.strip()
    if len(remaining) <= max_chars:
        return (remaining,) if remaining else ()

    pieces: list[str] = []
    while len(remaining) > max_chars:
        end = _split_index(remaining, max_chars)
        pieces.append(remaining[:end].strip())
        remaining = remaining[end:].strip()
    if remaining:
        pieces.append(remaining)
    return tuple(pieces)


def _split_index(text: str, max_chars: int) -> int:
    window = text[: max_chars + 1]
    lower_bound = max(32, max_chars // 3)
    for separator in (", ", " - ", " "):
        index = window.rfind(separator)
        if index >= lower_bound:
            if separator == ", ":
                return index + 1
            return index
    return max_chars
