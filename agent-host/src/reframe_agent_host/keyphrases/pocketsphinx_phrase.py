from __future__ import annotations

import numpy as np

from reframe_agent_host.keyphrases.aliases import phrase_alias_map
from reframe_agent_host.keyphrases.types import KeyphraseDetection, KeyphraseKind
from reframe_agent_host.keyphrases.pocketsphinx_helpers import (
    decoder_config,
    float_samples_to_int16,
    matched_phrase,
    normalize_phrase,
    phrase_grammar,
    phrase_end_sample,
)


class PocketSphinxPhraseSpotter:
    def __init__(
        self,
        phrase_kinds: dict[str, KeyphraseKind],
        check_interval_frames: int = 4,
        gain: float = 4.0,
        max_buffer_ms: int = 2_000,
    ) -> None:
        from pocketsphinx import Decoder

        phrase_kinds = {
            normalized: kind
            for phrase, kind in phrase_kinds.items()
            if (normalized := normalize_phrase(phrase))
        }
        if not phrase_kinds:
            raise ValueError("At least one phrase is required.")
        self._grammar_phrases = tuple(phrase_kinds)
        self._phrase_aliases = phrase_alias_map(phrase_kinds)

        self._check_interval_frames = max(1, check_interval_frames)
        self._gain = gain
        self._buffer_samples = 0
        self._buffer_start_sample = 0
        self._processed_samples = 0
        self._max_buffer_samples = max(1, int(16_000 * max_buffer_ms / 1000))
        self._frames_since_check = 0
        self._frames: list[np.ndarray] = []
        self._decoder = Decoder(decoder_config())
        self._decoder.add_jsgf_string(
            "reframewake",
            phrase_grammar(self._grammar_phrases),
        )
        self._decoder.activate_search("reframewake")
        self._decoder.start_utt()
        self._last_hypstr: str | None = None
        self._closed = False
        self._detection_emitted = False

    @property
    def last_hypstr(self) -> str | None:
        return self._last_hypstr

    def append(self, frame: np.ndarray) -> None:
        mono_frame = np.asarray(frame, dtype=np.float32).reshape(-1)
        self._frames.append(mono_frame)
        self._buffer_samples += len(mono_frame)
        self._processed_samples += len(mono_frame)
        self._trim_buffer()
        self._frames_since_check += 1
        pcm = float_samples_to_int16(mono_frame, gain=self._gain)
        self._decoder.process_raw(pcm.tobytes(), False, False)

    def detect(self, force: bool = False) -> KeyphraseDetection | None:
        if self._detection_emitted:
            return None
        if not self._frames:
            return None
        if not force and self._frames_since_check < self._check_interval_frames:
            return None

        self._frames_since_check = 0
        hypothesis = self._decoder.hyp()
        if hypothesis is None:
            self._last_hypstr = None
            return None

        hypstr = normalize_phrase(str(hypothesis.hypstr))
        self._last_hypstr = hypstr
        match = matched_phrase(hypstr, self._phrase_aliases)
        if match is None:
            return None

        self._detection_emitted = True
        return KeyphraseDetection(
            kind=match.kind,
            phrase=match.phrase,
            hypstr=hypstr,
            confirmed=True,
            phrase_end_sample=self._phrase_end_sample(match.matched_phrase),
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._decoder.end_utt()

    def _trim_buffer(self) -> None:
        extra_samples = self._buffer_samples - self._max_buffer_samples
        while extra_samples > 0 and self._frames:
            first_frame = self._frames[0]
            if len(first_frame) <= extra_samples:
                self._frames.pop(0)
                self._buffer_samples -= len(first_frame)
                self._buffer_start_sample += len(first_frame)
                extra_samples -= len(first_frame)
                continue

            self._frames[0] = first_frame[extra_samples:]
            self._buffer_samples -= extra_samples
            self._buffer_start_sample += extra_samples
            break

    def _phrase_end_sample(self, matched_phrase: str) -> int | None:
        absolute_sample = phrase_end_sample(tuple(self._decoder.seg()), matched_phrase)
        if absolute_sample is None:
            return None
        return max(0, absolute_sample - self._buffer_start_sample)


class PocketSphinxPhraseConfirmationSpotter(PocketSphinxPhraseSpotter):
    def __init__(
        self,
        phrases: tuple[str, ...],
        kind: KeyphraseKind,
        check_interval_frames: int = 4,
        gain: float = 4.0,
        max_buffer_ms: int = 2_000,
    ) -> None:
        super().__init__(
            {phrase: kind for phrase in phrases},
            check_interval_frames=check_interval_frames,
            gain=gain,
            max_buffer_ms=max_buffer_ms,
        )
