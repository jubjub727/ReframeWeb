from __future__ import annotations

from reframe_memory import Provider, ProviderNode


MAGIC_DO_NOTHING_MODEL_ID = "magic:do-nothing"
MAGIC_DO_NOTHING_BAML_SURFACE = "MagicDoNothing"
MAGIC_DO_NOTHING_CLIENT_NAME = "MagicDoNothing"
MAGIC_DO_NOTHING_TAGS = ("magic-provider", "do-nothing", "silent")


def magic_do_nothing_provider() -> Provider:
    return Provider(
        name="Magic provider: do nothing",
        description=(
            "A built-in no-op provider that returns an empty task result "
            "without calling an LLM."
        ),
        baml_surface=MAGIC_DO_NOTHING_BAML_SURFACE,
        model_id=MAGIC_DO_NOTHING_MODEL_ID,
    )


def is_magic_do_nothing_provider(provider: ProviderNode) -> bool:
    return (
        provider.content.baml_surface == MAGIC_DO_NOTHING_BAML_SURFACE
        and provider.content.model_id == MAGIC_DO_NOTHING_MODEL_ID
    )
