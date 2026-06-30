from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from reframe_agent_host.voice.microphone import AudioInputConfig
from reframe_agent_host.baml_client import types
from reframe_agent_host.keyphrases import (
    KeyphraseDetection,
    KeyphraseSpotterConfig,
)
from reframe_agent_host.speech.transcription import Transcript, WhisperTranscriberConfig
from reframe_agent_host.speech.triggers import TriggerPhraseConfig, TriggerPhraseDetection
from reframe_agent_host.voice.activity import DetectedUtterance, VoiceActivityConfig


VoicePipelineEventHandler = Callable[[str, str], None]


@dataclass(frozen=True)
class VoicePipelineConfig:
    audio: AudioInputConfig
    voice_activity: VoiceActivityConfig
    keyphrases: KeyphraseSpotterConfig
    triggers: TriggerPhraseConfig
    transcription: WhisperTranscriberConfig
    conversation_mode: types.ConversationMode
    playback_state: types.PlaybackState
    plan_enabled: bool = True
    listen_timeout_seconds: float = 0.0
    post_activation_command_window_ms: int = 700
    debug_audio_dir: str | None = None
    debug_audio_seconds: float = 8.0
    debug_audio_period_seconds: float = 0.0


@dataclass(frozen=True)
class VoiceTurnTimings:
    model_prepare_seconds: float
    keyphrase_wait_seconds: float | None
    listen_seconds: float
    wait_for_speech_seconds: float | None
    speech_capture_wall_seconds: float | None
    vad_endpoint_delay_estimate_seconds: float
    post_vad_transcript_seconds: float | None
    post_vad_plan_seconds: float | None
    estimated_user_stop_to_transcript_seconds: float | None
    estimated_user_stop_to_plan_seconds: float | None
    transcription_seconds: float | None
    planning_seconds: float | None
    total_seconds: float

    def to_dict(self) -> dict[str, float | None]:
        return {
            "model_prepare_seconds": self.model_prepare_seconds,
            "keyphrase_wait_seconds": self.keyphrase_wait_seconds,
            "listen_seconds": self.listen_seconds,
            "wait_for_speech_seconds": self.wait_for_speech_seconds,
            "speech_capture_wall_seconds": self.speech_capture_wall_seconds,
            "vad_endpoint_delay_estimate_seconds": (
                self.vad_endpoint_delay_estimate_seconds
            ),
            "post_vad_transcript_seconds": self.post_vad_transcript_seconds,
            "post_vad_plan_seconds": self.post_vad_plan_seconds,
            "estimated_user_stop_to_transcript_seconds": (
                self.estimated_user_stop_to_transcript_seconds
            ),
            "estimated_user_stop_to_plan_seconds": (
                self.estimated_user_stop_to_plan_seconds
            ),
            "transcription_seconds": self.transcription_seconds,
            "planning_seconds": self.planning_seconds,
            "total_seconds": self.total_seconds,
        }


@dataclass(frozen=True)
class VoiceTurnResult:
    mode: types.ConversationMode
    mode_switched: bool
    keyphrase_detection: KeyphraseDetection | None
    trigger_detection: TriggerPhraseDetection | None
    routed_transcript: str
    ignored: bool
    utterance: DetectedUtterance | None
    transcript: Transcript | None
    plan: types.AgentTurnPlan | None
    timings: VoiceTurnTimings

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "mode_switched": self.mode_switched,
            "keyphrase_detection": (
                {
                    "kind": self.keyphrase_detection.kind,
                    "phrase": self.keyphrase_detection.phrase,
                    "hypstr": self.keyphrase_detection.hypstr,
                    "confirmed": self.keyphrase_detection.confirmed,
                    "phrase_end_sample": (
                        self.keyphrase_detection.phrase_end_sample
                    ),
                }
                if self.keyphrase_detection is not None
                else None
            ),
            "trigger_detection": (
                {
                    "kind": self.trigger_detection.kind,
                    "phrase": self.trigger_detection.phrase,
                    "routed_transcript": self.trigger_detection.routed_transcript,
                }
                if self.trigger_detection is not None
                else None
            ),
            "routed_transcript": self.routed_transcript,
            "ignored": self.ignored,
            "utterance": (
                {
                    "sample_rate": self.utterance.sample_rate,
                    "duration_seconds": self.utterance.duration_seconds,
                    "forced_end": self.utterance.forced_end,
                }
                if self.utterance is not None
                else None
            ),
            "transcript": (
                self.transcript.to_dict()
                if self.transcript is not None
                else None
            ),
            "plan": self.plan.model_dump(mode="json") if self.plan is not None else None,
            "timings": self.timings.to_dict(),
        }


@dataclass(frozen=True)
class CaptureResult:
    conversation_mode: types.ConversationMode
    keyphrase_detection: KeyphraseDetection | None
    utterance: DetectedUtterance | None
    mode_switched: bool
    keyphrase_wait_seconds: float | None
    listen_seconds: float
    wait_for_speech_seconds: float | None
    speech_capture_wall_seconds: float | None
