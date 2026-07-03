from __future__ import annotations

import argparse
from datetime import datetime
import json
import sys

from reframe_agent_host.voice.microphone import AudioInputConfig
from reframe_agent_host.baml_client import types
from reframe_agent_host.commands.timing import TimedEventPrinter, print_timing_summary
from reframe_agent_host.keyphrases import KeyphraseSpotterConfig
from reframe_agent_host.speech.transcription import (
    WhisperGpuRuntimeError,
    WhisperTranscriberConfig,
)
from reframe_agent_host.speech.triggers import TriggerPhraseConfig
from reframe_agent_host.voice.activity import VoiceActivityConfig
from reframe_agent_host.voice.pipeline import VoicePipelineConfig, VoiceTurnPipeline
from reframe_memory import Conversation, Session, open_memory_database


async def run_voice_turn(args: argparse.Namespace) -> int:
    if args.turns < 0:
        print("[error] --turns must be 0 or greater", file=sys.stderr)
        return 2

    config = await _prepared_voice_pipeline_config(args)
    pipeline = VoiceTurnPipeline(config)
    results = []
    turn_index = 0
    try:
        while args.turns == 0 or turn_index < args.turns:
            turn_index += 1
            if args.turns != 1:
                print(f"[turn {turn_index}] starting", file=sys.stderr)

            result = await pipeline.run_once(on_event=TimedEventPrinter())
            results.append(result)
            print(json.dumps(_result_payload(result, config), indent=2))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        if results:
            print_timing_summary(results)
        return 130
    except TimeoutError as error:
        print(f"[timeout] {error}", file=sys.stderr)
        if results:
            print_timing_summary(results)
        return 2
    except WhisperGpuRuntimeError as error:
        print(f"[gpu] {error}", file=sys.stderr)
        return 3

    if args.turns != 1:
        print_timing_summary(results)
    return 0


async def _prepared_voice_pipeline_config(args: argparse.Namespace) -> VoicePipelineConfig:
    if not args.no_task_choice:
        await _ensure_voice_memory_context(args)
    return _voice_pipeline_config(args)


async def _ensure_voice_memory_context(args: argparse.Namespace) -> None:
    if args.conversation_id is not None and args.session_id is None:
        print(
            "[error] --conversation-id requires --session-id",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if args.session_id is not None and args.conversation_id is not None:
        return

    database = await open_memory_database()
    try:
        await database.apply_schema()
        await database.ensure_roots()

        if args.session_id is None:
            session = await database.sessions.create(
                Session(name=_timestamped_name("Voice session")),
                tags=("voice",),
            )
            args.session_id = session.id

        if args.conversation_id is None:
            conversation = await database.conversations.create(
                args.session_id,
                Conversation(name=_timestamped_name("Voice conversation")),
                tags=("voice",),
            )
            args.conversation_id = conversation.id
    finally:
        await database.close()

    print(
        f"[memory] session_id={args.session_id} conversation_id={args.conversation_id}",
        file=sys.stderr,
    )


def _timestamped_name(prefix: str) -> str:
    return f"{prefix} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def _result_payload(result, config: VoicePipelineConfig) -> dict[str, object]:
    payload = result.to_dict()
    payload["session_id"] = config.session_id
    payload["conversation_id"] = config.conversation_id
    return payload


def _voice_pipeline_config(args: argparse.Namespace) -> VoicePipelineConfig:
    return VoicePipelineConfig(
        audio=_audio_config(args),
        voice_activity=_voice_activity_config(args),
        keyphrases=_keyphrase_config(args),
        triggers=TriggerPhraseConfig(
            trigger_words=tuple(args.wake_keyword),
            conversation_on_phrases=tuple(args.conversation_on_phrase),
        ),
        transcription=_transcription_config(args),
        conversation_mode=types.ConversationMode(args.mode),
        task_choice_enabled=not args.no_task_choice,
        session_id=args.session_id,
        conversation_id=args.conversation_id,
        listen_timeout_seconds=args.listen_timeout_seconds,
        post_activation_command_window_ms=args.post_activation_command_window_ms,
        debug_audio_dir=args.debug_audio_dir,
        debug_audio_seconds=args.debug_audio_seconds,
        debug_audio_period_seconds=args.debug_audio_period_seconds,
    )


def _audio_config(args: argparse.Namespace) -> AudioInputConfig:
    return AudioInputConfig(
        sample_rate=args.sample_rate,
        input_sample_rate=args.input_sample_rate or None,
        input_gain=args.input_gain,
        chunk_ms=args.chunk_ms,
        channels=args.input_channels,
        channel=args.input_channel,
        device=_coerce_device(args.device),
    )


def _voice_activity_config(args: argparse.Namespace) -> VoiceActivityConfig:
    return VoiceActivityConfig(
        sample_rate=args.sample_rate,
        chunk_ms=args.chunk_ms,
        detector=args.vad,
        threshold=args.vad_threshold,
        min_silence_ms=args.min_silence_ms,
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


def _transcription_config(args: argparse.Namespace) -> WhisperTranscriberConfig:
    return WhisperTranscriberConfig(
        model_size_or_path=args.whisper_model,
        compute_type=args.whisper_compute_type,
        language=args.language,
        beam_size=args.beam_size,
    )


def _coerce_device(value: str | None) -> int | str | None:
    if value is None:
        return None

    try:
        return int(value)
    except ValueError:
        return value
