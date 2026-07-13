from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from baml_sdk import turn_context as baml_turn_context
from reframe_agent_host.keyphrases import KeyphraseSpotterConfig
from reframe_agent_host.speech.transcription import WhisperTranscriberConfig
from reframe_agent_host.speech.triggers import TriggerPhraseConfig
from reframe_agent_host.voice.activity import VoiceActivityConfig
from reframe_agent_host.voice.microphone import AudioInputConfig


VoicePipelineEventHandler = Callable[[str, str], None]


@dataclass(frozen=True)
class VoicePipelineConfig:
    audio: AudioInputConfig
    voice_activity: VoiceActivityConfig
    keyphrases: KeyphraseSpotterConfig
    triggers: TriggerPhraseConfig
    transcription: WhisperTranscriberConfig
    conversation_mode: baml_turn_context.ConversationMode
    task_choice_enabled: bool = True
    session_id: str | None = None
    conversation_id: str | None = None
    listen_timeout_seconds: float = 0.0
    post_activation_command_window_ms: int = 700
    debug_audio_dir: str | None = None
    debug_audio_seconds: float = 8.0
    debug_audio_period_seconds: float = 0.0
