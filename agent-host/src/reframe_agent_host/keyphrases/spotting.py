from __future__ import annotations

from reframe_agent_host.keyphrases.types import (
    KeyphraseDetection,
    KeyphraseKind,
    KeyphraseSpotterConfig,
)
from reframe_agent_host.keyphrases.pocketsphinx_phrase import (
    PocketSphinxPhraseConfirmationSpotter,
    PocketSphinxPhraseSpotter,
)


__all__ = [
    "KeyphraseDetection",
    "KeyphraseKind",
    "KeyphraseSpotterConfig",
    "PocketSphinxPhraseConfirmationSpotter",
    "PocketSphinxPhraseSpotter",
]
