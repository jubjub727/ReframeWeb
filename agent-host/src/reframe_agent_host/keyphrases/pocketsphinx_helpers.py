from __future__ import annotations

import os
from pathlib import Path
import re

import numpy as np

from reframe_agent_host.keyphrases.types import KeyphraseKind, PhraseMatch


def decoder_config():
    from pocketsphinx import Config, get_model_path

    model_path = Path(get_model_path()) / "en-us"
    config = Config()
    config["hmm"] = str(model_path / "en-us")
    config["dict"] = str(model_path / "cmudict-en-us.dict")
    config["lm"] = str(model_path / "en-us.lm.bin")
    config["samprate"] = 16_000
    config["logfn"] = os.devnull
    return config


def keyphrase_decoder_config(phrase: str, threshold: float):
    config = decoder_config()
    config.set_string("lm", None)
    config["keyphrase"] = phrase
    config["kws_threshold"] = threshold
    return config


def phrase_grammar(phrases: tuple[str, ...]) -> str:
    alternatives = " | ".join(sorted(phrases, key=len, reverse=True))
    return f"#JSGF V1.0; grammar reframewake; public <phrase> = {alternatives};"


def matched_phrase(
    hypstr: str,
    phrase_map: dict[str, tuple[str, KeyphraseKind]],
) -> PhraseMatch | None:
    normalized_hypstr = normalize_phrase(hypstr)
    for matched in sorted(
        phrase_map,
        key=lambda value: (len(value.split()), len(value)),
        reverse=True,
    ):
        if contains_phrase(normalized_hypstr, matched):
            phrase, kind = phrase_map[matched]
            return PhraseMatch(phrase=phrase, matched_phrase=matched, kind=kind)
    return None


def contains_phrase(hypstr: str, phrase: str) -> bool:
    hyp_words = hypstr.split()
    phrase_words = phrase.split()
    if not phrase_words or len(phrase_words) > len(hyp_words):
        return False

    phrase_length = len(phrase_words)
    return any(
        hyp_words[index : index + phrase_length] == phrase_words
        for index in range(len(hyp_words) - phrase_length + 1)
    )


def normalize_phrase(value: str) -> str:
    words = [
        re.sub(r"\(\d+\)$", "", word)
        for word in value.lower().strip().split()
    ]
    return " ".join(words)


def phrase_sample_span(
    segments: tuple[object, ...],
    phrase: str,
) -> tuple[int, int] | None:
    phrase_words = phrase.split()
    if not phrase_words:
        return None

    words = [
        segment
        for segment in segments
        if normalize_phrase(str(getattr(segment, "word", ""))).strip("<>") not in (
            "s",
            "/s",
            "sil",
        )
    ]
    word_values = [normalize_phrase(str(getattr(segment, "word", ""))) for segment in words]

    for index in range(len(word_values) - len(phrase_words) + 1):
        if word_values[index : index + len(phrase_words)] == phrase_words:
            start_frame = int(getattr(words[index], "start_frame"))
            end_frame = int(getattr(words[index + len(phrase_words) - 1], "end_frame"))
            return start_frame * 160, (end_frame + 1) * 160
    return None


def float_samples_to_int16(samples: np.ndarray, gain: float = 1.0) -> np.ndarray:
    mono_frame = np.asarray(samples, dtype=np.float32).reshape(-1)
    if gain > 0:
        mono_frame = mono_frame * gain
    peak = float(np.max(np.abs(mono_frame))) if len(mono_frame) else 0.0
    if 0.002 <= peak < 0.4:
        mono_frame = mono_frame * min(8.0, 0.65 / peak)
    mono_frame = np.clip(mono_frame, -1.0, 1.0)
    return (mono_frame * 32767.0).astype(np.int16)
