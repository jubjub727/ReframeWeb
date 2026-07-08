from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from reframe_agent_host.keyphrases import (
    KeyphraseDetection,
    PocketSphinxPhraseSpotter,
)
from reframe_agent_host.voice.capture_state import CaptureState
from reframe_agent_host.voice.types import VoicePipelineConfig


EventEmitter = Callable[[str, str], None]


@dataclass(frozen=True)
class KeyphraseGateResult:
    detection: KeyphraseDetection
    conversation_enabled: bool
    replay_frames: list[np.ndarray]


class VoiceKeyphraseGate:
    def __init__(self, config: VoicePipelineConfig) -> None:
        self._config = config

    def start(
        self,
        state: CaptureState,
        emit: EventEmitter,
    ) -> None:
        state.keyphrase_spotter = self._phrase_spotter()
        emit("keyphrase", "waiting for " + ", ".join(self._phrases()))

    def accept(
        self,
        frame: np.ndarray,
        state: CaptureState,
        listen_started_at: float,
        emit: EventEmitter,
    ) -> KeyphraseGateResult | None:
        state.keyphrase_carry_frames.append(frame)
        if state.keyphrase_spotter is None:
            return None

        state.keyphrase_spotter.append(frame)
        detection = state.keyphrase_spotter.detect()
        if detection is None:
            return None

        emit("keyphrase", f"detected {detection.phrase!r} as {detection.hypstr!r}")
        state.keyphrase_detection = detection
        state.keyphrase_wait_seconds = time.perf_counter() - listen_started_at
        replay_frames = self._replay_frames(state, detection)
        state.close_spotters()
        return KeyphraseGateResult(
            detection,
            detection.kind == "conversation_on",
            replay_frames,
        )

    def _replay_frames(
        self,
        state: CaptureState,
        detection: KeyphraseDetection,
    ) -> list[np.ndarray]:
        if state.keyphrase_spotter is None:
            return []
        if detection.kind == "conversation_on":
            return state.keyphrase_spotter.confirmation_frames_for_detection(
                detection,
                self._config.keyphrases.conversation_on_confirm_window_ms,
            )
        return state.keyphrase_spotter.replay_frames_for_detection(
            detection,
            self._config.keyphrases.replay_pre_ms,
        )

    def _phrase_spotter(self) -> PocketSphinxPhraseSpotter:
        return PocketSphinxPhraseSpotter(
            phrase_kinds={
                **{phrase: "wake_command" for phrase in self._config.keyphrases.trigger_words},
                **{
                    phrase: "conversation_on"
                    for phrase in self._config.keyphrases.conversation_on_phrases
                },
            },
            check_interval_frames=max(
                1,
                round(
                    self._config.keyphrases.check_interval_ms
                    / self._config.voice_activity.chunk_ms
                ),
            ),
            gain=self._config.keyphrases.gain,
            max_buffer_ms=max(
                self._config.keyphrases.carry_ms,
                self._config.keyphrases.conversation_on_confirm_window_ms,
            ),
            kws_threshold=self._config.keyphrases.kws_threshold,
        )

    def _phrases(self) -> tuple[str, ...]:
        return (
            self._config.keyphrases.trigger_words
            + self._config.keyphrases.conversation_on_phrases
        )
