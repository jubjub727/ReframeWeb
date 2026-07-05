from __future__ import annotations

import argparse
from datetime import datetime
import os
import sys
import time

from reframe_agent_host.voice.microphone import AudioInputConfig
import baml_sdk as types
from reframe_agent_host.commands.timing import print_timing_summary
from reframe_agent_host.commands.voice_loop import run_voice_turn_loop
from reframe_agent_host.keyphrases import KeyphraseSpotterConfig
from reframe_agent_host.voice.audio_calibration import load_audio_calibration
from reframe_agent_host.speech.transcription import (
    WhisperGpuRuntimeError,
    WhisperTranscriberConfig,
)
from reframe_agent_host.speech.triggers import TriggerPhraseConfig
from reframe_agent_host.voice.activity import VoiceActivityConfig
from reframe_agent_host.voice.pipeline import VoicePipelineConfig, VoiceTurnPipeline
from reframe_memory import (
    Conversation,
    ConversationMessageNode,
    MemoryNode,
    RetrievedConversation,
    RetrievedMemoryContext,
    RetrievedSessionContext,
    Session,
    SessionMemoryNode,
    TaskNode,
    open_memory_database,
)


async def run_voice_turn(args: argparse.Namespace) -> int:
    if args.turns < 0:
        print("[error] --turns must be 0 or greater", file=sys.stderr)
        return 2

    debug_output = args.debug_output or args.verbose_context
    _configure_baml_logging(debug_output)
    config = await _prepared_voice_pipeline_config(args)
    pipeline = VoiceTurnPipeline(config)
    results = []
    try:
        await run_voice_turn_loop(
            turns=args.turns,
            pipeline=pipeline,
            results=results,
            debug_output=debug_output,
            event_handler_factory=lambda turn_started_at: _VoiceTurnEventPrinter(
                debug_output=debug_output,
                turn_started_at=turn_started_at,
            ),
            result_handler=lambda result: _print_turn_result(
                result,
                config,
                debug_output=debug_output,
                verbose_context=args.verbose_context,
            ),
        )
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        if debug_output and results:
            print_timing_summary(results)
        return 130
    except TimeoutError as error:
        print(f"[timeout] {error}", file=sys.stderr)
        if debug_output and results:
            print_timing_summary(results)
        return 2
    except WhisperGpuRuntimeError as error:
        print(f"[gpu] {error}", file=sys.stderr)
        return 3

    if debug_output and args.turns != 1:
        print_timing_summary(results)
    return 0


def _configure_baml_logging(debug_output: bool) -> None:
    if not debug_output:
        os.environ["BAML_LOG"] = "OFF"


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

    if args.debug_output or args.verbose_context:
        print(
            f"[memory] session_id={args.session_id} conversation_id={args.conversation_id}",
            file=sys.stderr,
        )


def _timestamped_name(prefix: str) -> str:
    return f"{prefix} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


class _VoiceTurnEventPrinter:
    _DISPLAY_NAMES = {
        "primitive-dispatch": "response-items",
        "primitive-dispatched": "response-items",
    }
    _LATENCY_STAGES = {
        "task-chosen": "task_choice",
        "memory-search-hints": "memory_search",
        "search-depths": "search_depth",
        "memory-relevance-decision": "memory_relevance",
        "task-prompt-generated": "task_prompt",
        "task-executed": "task_execution",
    }

    def __init__(self, *, debug_output: bool, turn_started_at: float) -> None:
        self._debug_output = debug_output
        self._turn_started_at = turn_started_at
        self._startup_reported = False

    def __call__(self, stage: str, message: str) -> None:
        if stage == "input-started":
            self._print_live("[Input Started]")
            return
        if stage == "input-stopped":
            self._print_live("[Input Stopped]")
            return

        if not self._debug_output:
            if stage == "listening":
                if self._startup_reported:
                    self._print_live("[ready]")
                else:
                    self._startup_reported = True
                    self._print_live(
                        "[startup "
                        f"{_latency(time.perf_counter() - self._turn_started_at)}] "
                        "ready",
                    )
            elif stage == "human-reply":
                self._print_live(f"human_reply: {_single_line(message, limit=None)}")
            elif stage == "agent-thought":
                self._print_live(f"agent_thought: {_single_line(message, limit=None)}")
            elif stage == "agent-reply":
                self._print_live(f"agent_reply: {_single_line(message, limit=None)}")
            elif stage == "conversation-mode":
                self._print_live(
                    f"conversation_mode: {_single_line(message, limit=None)}"
                )
            elif stage == "task-chosen":
                selected = _selected_task_from_event(message)
                if selected:
                    self._print_live(f"selected: {selected}")
                latency = _event_latency(message)
                if latency is not None:
                    self._print_live(f"[task_choice {latency}]")
            elif stage in self._LATENCY_STAGES:
                latency = _event_latency(message)
                if latency is not None:
                    label = self._LATENCY_STAGES[stage]
                    self._print_live(f"[{label} {latency}]")
            return

        if stage in {
            "preparing",
            "ready",
            "listening",
            "audio",
            "transcribing",
            "transcript",
            "human-reply",
            "trigger",
            "keyphrase",
            "speech",
            "task-choice",
            "memory-search",
            "search-depth",
            "memory-retrieval",
            "memory-relevance",
            "task-prompt",
            "task-execution",
            "primitive-dispatch",
            "agent-reply",
            "agent-thought",
            "conversation-mode",
            "tts-error",
            "conversation-context",
            "debug-audio",
        }:
            label = self._DISPLAY_NAMES.get(stage, stage)
            self._print_live(f"[{label}] {message}")

    def _print_live(self, message: str) -> None:
        print(message, flush=True)


def _print_turn_result(
    result,
    config: VoicePipelineConfig,
    *,
    debug_output: bool,
    verbose_context: bool,
) -> None:
    if not debug_output:
        return

    print()
    print("Turn summary")
    print(f"session_id: {config.session_id or 'NONE'}")
    print(f"conversation_id: {config.conversation_id or 'NONE'}")
    if result.routed_transcript:
        print(f"human_reply: {_single_line(result.routed_transcript, limit=None)}")

    if result.transcript is not None:
        print(
            "transcription: "
            f"{_latency(result.timings.transcription_seconds)}"
        )
    if result.task_choice is not None:
        print(
            "task_choice: "
            f"{result.task_choice.selected_task_id} "
            f"confidence={result.task_choice.confidence:.2f} "
            f"latency={_latency(result.timings.task_choice_seconds)}"
        )
        if result.task_choice.agent_thought:
            print(
                "agent_thought: "
                f"{_single_line(result.task_choice.agent_thought, limit=None)}"
            )
    if result.memory_search_hints is not None:
        hints = result.memory_search_hints
        print(
            "memory_search_hints: "
            f"tags_any={len(hints.tags.any_of)} "
            f"tags_none={len(hints.tags.none_of)} "
            f"strings_contains={len(hints.strings.contains)} "
            f"latency={_latency(result.timings.memory_search_seconds)}"
        )
    if result.search_depths is not None:
        print(
            "search_depth: "
            f"domains={len(result.search_depths.depths)} "
            f"latency={_latency(result.timings.search_depth_seconds)}"
        )
    if result.retrieved_memories is not None:
        print(
            "memory_retrieval: "
            f"{_retrieval_counts(result.retrieved_memories)} "
            f"latency={_latency(result.timings.memory_retrieval_seconds)}"
        )
        if verbose_context:
            _print_retrieved_memories(result.retrieved_memories)
    if result.relevance_decision is not None:
        print(
            "memory_relevance: "
            f"kept_ids={result.relevance_decision.kept_memory_ids} "
            f"latency={_latency(result.timings.memory_relevance_seconds)}"
        )
    if result.relevant_memories is not None:
        print(
            "relevant_memory_context: "
            f"{_retrieval_counts(result.relevant_memories)}"
        )
        if verbose_context:
            _print_retrieved_memories(result.relevant_memories, "Relevant memories")
    if result.task_prompt is not None:
        print(
            "task_prompt: "
            f"chars={len(result.task_prompt.full_task_prompt)} "
            f"latency={_latency(result.timings.task_prompt_seconds)}"
        )
    if result.task_execution is not None:
        print(
            "task_execution: "
            f"returns={len(result.task_execution.returns)} "
            f"latency={_latency(result.timings.task_execution_seconds)}"
        )
    if result.primitive_dispatch is not None:
        print(
            "response_items: "
            f"records={len(result.primitive_dispatch.records)} "
            f"latency={_latency(result.timings.primitive_dispatch_seconds)}"
        )
        _print_conversation_returns(result.primitive_dispatch.records)


def _print_conversation_lines(result) -> None:
    if result.routed_transcript:
        print(f"human_reply: {_single_line(result.routed_transcript, limit=None)}")

    if result.task_choice is not None and result.task_choice.agent_thought:
        print(
            "agent_thought: "
            f"{_single_line(result.task_choice.agent_thought, limit=None)}"
        )

    if result.primitive_dispatch is not None:
        _print_conversation_returns(result.primitive_dispatch.records)


def _print_conversation_returns(records) -> None:
    for record in records:
        if record.name in {"agent_thought", "agent_reply"}:
            print(f"{record.name}: {_single_line(record.detail, limit=None)}")
        elif record.status in {"unsupported", "malformed"}:
            print(f"agent_reply: {_single_line(record.detail, limit=None)}")


def _depth_summary(depths: types.SearchDepthDecision) -> str:
    pieces = []
    for domain, timestamps in depths.depths.items():
        pieces.append(
            f"{domain}(created>{timestamps.created_after}, "
            f"updated>{timestamps.updated_after}, read>{timestamps.read_after})"
        )
    return "; ".join(pieces)


def _retrieval_counts(memories: RetrievedMemoryContext) -> str:
    tasks = len(memories.task_catalog.tasks)
    current_memories = len(memories.current_session_memories)
    sessions = len(memories.past_conversation_context.sessions)
    conversations = sum(
        len(session.conversations)
        for session in memories.past_conversation_context.sessions
    )
    messages = sum(
        len(conversation.messages)
        for session in memories.past_conversation_context.sessions
        for conversation in session.conversations
    )
    session_memories = sum(
        len(session.session_memories)
        for session in memories.past_conversation_context.sessions
    )
    return (
        f"tasks={tasks} current_session_memories={current_memories} "
        f"past_sessions={sessions} conversations={conversations} "
        f"messages={messages} past_session_memories={session_memories}"
    )


def _print_retrieved_memories(
    memories: RetrievedMemoryContext,
    label: str = "Retrieved memories",
) -> None:
    print()
    print(label)
    _print_session_memories(
        "Current session memories",
        memories.current_session_memories,
    )
    _print_tasks(memories.task_catalog.tasks)
    _print_past_sessions(memories.past_conversation_context.sessions)


def _print_tasks(tasks: tuple[TaskNode, ...]) -> None:
    print()
    print(f"Task catalog ({len(tasks)})")
    if not tasks:
        print("  none")
        return
    for task in tasks:
        print(f"  - {task.content.name} [{task.id}]")
        print(f"    tags: {_tags(task)}")
        print(f"    description: {_single_line(task.content.description, limit=None)}")
        print(f"    input: {_single_line(task.content.input, limit=None)}")
        print(f"    output: {_single_line(task.content.output, limit=None)}")


def _print_past_sessions(sessions: tuple[RetrievedSessionContext, ...]) -> None:
    print()
    print(f"Past conversation context ({len(sessions)} sessions)")
    if not sessions:
        print("  none")
        return
    for session in sessions:
        marker = "matched" if session.matched else "wrapper"
        print(f"  - Session {session.session.content.name} [{session.session.id}] {marker}")
        _print_session_memories("    Session memories", session.session_memories)
        _print_conversations(session.conversations)


def _print_conversations(conversations: tuple[RetrievedConversation, ...]) -> None:
    print(f"    Conversations ({len(conversations)})")
    if not conversations:
        print("      none")
        return
    for conversation in conversations:
        _print_conversation(conversation)


def _print_conversation(conversation: RetrievedConversation) -> None:
    marker = "matched" if conversation.matched else "wrapper"
    node = conversation.conversation
    print(f"      - {node.content.name} [{node.id}] {marker}")
    print(f"        messages ({len(conversation.messages)})")
    if not conversation.messages:
        print("          none")
        return
    for message in conversation.messages:
        _print_message(message)


def _print_message(message: ConversationMessageNode) -> None:
    print(
        f"          - [{message.content.role}] {message.id}: "
        f"{_single_line(message.content.content, limit=None)}"
    )


def _print_session_memories(
    label: str,
    memories: tuple[SessionMemoryNode, ...],
) -> None:
    print()
    print(f"{label} ({len(memories)})")
    if not memories:
        print("  none")
        return
    for memory in memories:
        print(f"  - {memory.content.title} [{memory.id}]")
        print(f"    tags: {_tags(memory)}")
        print(f"    description: {_single_line(memory.content.description, limit=None)}")


def _tags(node: MemoryNode[object]) -> str:
    return ", ".join(node.tags) if node.tags else "none"


def _single_line(value: str, limit: int | None = 180) -> str:
    text = " ".join(value.split())
    if limit is None:
        return text
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _latency(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value < 1:
        return f"{value * 1000:.0f}ms"
    return f"{value:.3f}s"


def _event_latency(message: str) -> str | None:
    marker = message.rsplit("(", 1)
    if len(marker) != 2:
        return None
    value = marker[1].rstrip(")").strip()
    if not value.endswith("s"):
        return None
    try:
        return _latency(float(value[:-1]))
    except ValueError:
        return None


def _selected_task_from_event(message: str) -> str:
    text = message.strip()
    prefix = "selected:"
    if not text.lower().startswith(prefix):
        return ""
    selected = text[len(prefix) :].strip()
    latency_index = selected.rfind("(")
    if latency_index >= 0 and selected.endswith(")"):
        selected = selected[:latency_index].strip()
    return selected


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
        input_gain=_resolved_input_gain(args),
        limiter_ceiling=args.limiter_ceiling,
        chunk_ms=args.chunk_ms,
        channels=args.input_channels,
        channel=args.input_channel,
        device=_coerce_device(args.device),
    )


def _resolved_input_gain(args: argparse.Namespace) -> float:
    if args.input_gain is not None:
        return args.input_gain
    if args.ignore_audio_calibration:
        return 1.0

    calibration = load_audio_calibration(args.audio_calibration_file)
    if calibration is None:
        return 1.0
    return calibration.input_gain


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


def _transcription_config(args: argparse.Namespace) -> WhisperTranscriberConfig:
    return WhisperTranscriberConfig(
        model_size_or_path=args.whisper_model,
        compute_type=args.whisper_compute_type,
        language=args.language,
        beam_size=args.beam_size,
        initial_prompt=args.whisper_initial_prompt or None,
        normalize_audio=not args.no_transcription_normalization,
        normalization_target_rms=args.transcription_target_rms,
        normalization_max_gain=args.transcription_max_gain,
    )


def _coerce_device(value: str | None) -> int | str | None:
    if value is None:
        return None

    try:
        return int(value)
    except ValueError:
        return value
