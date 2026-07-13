from __future__ import annotations

import argparse

from baml_sdk import turn_context as baml_turn_context

from reframe_agent_host.keyphrases import KeyphraseSpotterConfig
from reframe_agent_host.speech.transcription import WhisperTranscriberConfig
from reframe_agent_host.speech.triggers import TriggerPhraseConfig
from reframe_agent_host.voice.activity import VoiceActivityConfig
from reframe_agent_host.voice.audio_calibration import load_audio_calibration
from reframe_agent_host.voice.microphone import AudioInputConfig
from reframe_agent_host.voice.pipeline_config import VoicePipelineConfig


def voice_pipeline_config(args: argparse.Namespace) -> VoicePipelineConfig:
    return VoicePipelineConfig(
        audio=audio_config(args),
        voice_activity=_voice_activity_config(args),
        keyphrases=_keyphrase_config(args),
        triggers=TriggerPhraseConfig(
            trigger_words=tuple(args.wake_keyword),
            conversation_on_phrases=tuple(args.conversation_on_phrase),
        ),
        transcription=transcription_config(args),
        conversation_mode=baml_turn_context.ConversationMode(args.mode),
        task_choice_enabled=not args.no_task_choice,
        session_id=args.session_id,
        conversation_id=args.conversation_id,
        listen_timeout_seconds=args.listen_timeout_seconds,
        post_activation_command_window_ms=args.post_activation_command_window_ms,
        debug_audio_dir=args.debug_audio_dir,
        debug_audio_seconds=args.debug_audio_seconds,
        debug_audio_period_seconds=args.debug_audio_period_seconds,
    )


def audio_config(args: argparse.Namespace) -> AudioInputConfig:
    return AudioInputConfig(
        sample_rate=args.sample_rate,
        input_sample_rate=args.input_sample_rate or None,
        input_gain=_resolved_input_gain(args),
        limiter_ceiling=args.limiter_ceiling,
        chunk_ms=args.chunk_ms,
        channels=args.input_channels,
        channel=args.input_channel,
        device=_coerce_device(args.device),
    )


def transcription_config(args: argparse.Namespace) -> WhisperTranscriberConfig:
    return WhisperTranscriberConfig(
        model_size_or_path=args.whisper_model,
        backend=args.transcriber,
        device=args.transcriber_device,
        compute_type=args.whisper_compute_type,
        cpu_compute_type=args.whisper_cpu_compute_type,
        allow_cpu_fallback=not args.no_cpu_fallback,
        whisper_cpp_bin=args.whisper_cpp_bin,
        whisper_cpp_model=args.whisper_cpp_model,
        whisper_cpp_extra_args=tuple(args.whisper_cpp_extra_args),
        language=args.language,
        beam_size=args.beam_size,
        initial_prompt=args.whisper_initial_prompt or None,
        normalize_audio=not args.no_transcription_normalization,
        normalization_target_rms=args.transcription_target_rms,
        normalization_max_gain=args.transcription_max_gain,
    )


def _resolved_input_gain(args: argparse.Namespace) -> float:
    if args.input_gain is not None:
        return args.input_gain
    if args.ignore_audio_calibration:
        return 1.0
    calibration = load_audio_calibration(args.audio_calibration_file)
    return calibration.input_gain if calibration is not None else 1.0


def _voice_activity_config(args: argparse.Namespace) -> VoiceActivityConfig:
    return VoiceActivityConfig(
        sample_rate=args.sample_rate,
        chunk_ms=args.chunk_ms,
        detector=args.vad,
        threshold=args.vad_threshold,
        min_silence_ms=args.min_silence_ms,
        final_silence_ms=args.final_silence_ms,
        speech_pad_ms=args.speech_pad_ms,
        pre_speech_ms=args.pre_speech_ms,
        min_utterance_ms=args.min_utterance_ms,
        max_utterance_seconds=args.max_utterance_seconds,
        energy_start_threshold=args.energy_start_threshold,
        energy_end_threshold=args.energy_end_threshold,
    )


def _keyphrase_config(args: argparse.Namespace) -> KeyphraseSpotterConfig:
    return KeyphraseSpotterConfig(
        trigger_words=tuple(args.wake_keyword),
        conversation_on_phrases=tuple(args.conversation_on_phrase),
        conversation_on_confirm_window_ms=args.conversation_on_confirm_window_ms,
        check_interval_ms=args.wake_check_ms,
        carry_ms=args.wake_carry_ms,
        replay_pre_ms=args.wake_replay_pre_ms,
        gain=args.wake_gain,
        kws_threshold=args.wake_threshold,
    )


def _coerce_device(value: str | None) -> int | str | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return value
