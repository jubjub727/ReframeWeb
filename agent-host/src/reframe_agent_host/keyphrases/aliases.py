from __future__ import annotations

from reframe_agent_host.keyphrases.types import KeyphraseKind


BUILT_IN_ALIASES: dict[str, tuple[str, ...]] = {
    "jarvis": (
        "gervais",
        "jervis",
        "jar viss",
    ),
    "conversation on": (
        "conversation one",
        "conservation on",
        "conservation one",
    ),
}


def phrase_alias_map(
    phrase_kinds: dict[str, KeyphraseKind],
) -> dict[str, tuple[str, KeyphraseKind]]:
    aliases: dict[str, tuple[str, KeyphraseKind]] = {}
    for phrase, kind in phrase_kinds.items():
        aliases[phrase] = (phrase, kind)
        for alias in BUILT_IN_ALIASES.get(phrase, ()):
            aliases[alias] = (phrase, kind)
    return aliases
