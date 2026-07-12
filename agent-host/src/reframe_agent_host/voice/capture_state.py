from __future__ import annotations

from collections import deque

import numpy as np

from baml_sdk import context as baml_context
from reframe_agent_host.keyphrases import (
    KeyphraseDetection,
    PocketSphinxPhraseSpotter,
)


class CaptureState:
    def __init__(
        self,
        conversation_mode: baml_context.ConversationMode,
        keyphrase_required: bool,
        keyphrase_carry_frames: deque[np.ndarray],
    ) -> None:
        self.conversation_mode = conversation_mode
        self.keyphrase_required = keyphrase_required
        self.keyphrase_carry_frames = keyphrase_carry_frames
        self.keyphrase_wait_seconds: float | None = None
        self.keyphrase_detection: KeyphraseDetection | None = None
        self.keyphrase_spotter: PocketSphinxPhraseSpotter | None = None
        self.mode_switched = False
        self.post_activation_deadline: float | None = None
        self.speech_started_at: float | None = None
        self.was_recording = False

    def close_spotters(self) -> None:
        if self.keyphrase_spotter is not None:
            self.keyphrase_spotter.close()
        self.keyphrase_spotter = None
