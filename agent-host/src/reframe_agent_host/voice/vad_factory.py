from __future__ import annotations

from reframe_agent_host.voice.vad_energy import EnergyVoiceActivityDetector
from reframe_agent_host.voice.vad_silero import SileroVoiceActivityDetector
from reframe_agent_host.voice.vad_types import (
    VoiceActivityConfig,
    VoiceActivityDetector,
)


def create_voice_activity_detector(config: VoiceActivityConfig) -> VoiceActivityDetector:
    if config.detector == "energy":
        return EnergyVoiceActivityDetector(config)

    if config.detector == "silero":
        return SileroVoiceActivityDetector(config)

    try:
        return SileroVoiceActivityDetector(config)
    except Exception:
        return EnergyVoiceActivityDetector(config)
