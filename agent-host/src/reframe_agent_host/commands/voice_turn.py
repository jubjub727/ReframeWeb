from __future__ import annotations

import argparse
from datetime import datetime
import os
import sys

from reframe_agent_host.agent_flow.machine_state import MachineStateError
from reframe_agent_host.commands.timing import print_timing_summary
from reframe_agent_host.commands.voice_config import voice_pipeline_config
from reframe_agent_host.commands.voice_loop import run_voice_turn_loop
from reframe_agent_host.commands.voice_output import VoiceTurnEventPrinter
from reframe_agent_host.commands.voice_result_output import print_turn_result
from reframe_agent_host.memory_readiness import (
    MemoryReadinessError,
    require_memory_ready,
)
from reframe_agent_host.speech.transcription import TranscriptionRuntimeError
from reframe_agent_host.voice.pipeline import VoiceTurnPipeline
from reframe_agent_host.voice.pipeline_config import VoicePipelineConfig
from reframe_memory import Conversation, Session, open_memory_database
from reframe_memory.ids import memory_node_record_id


async def run_voice_turn(args: argparse.Namespace) -> int:
    if args.turns < 0:
        print("[error] --turns must be 0 or greater", file=sys.stderr)
        return 2

    debug_output = args.debug_output or args.verbose_context
    _configure_baml_logging(debug_output)
    results = []
    try:
        config = await _prepared_voice_pipeline_config(args)
        await run_voice_turn_loop(
            turns=args.turns,
            pipeline=VoiceTurnPipeline(config),
            results=results,
            debug_output=debug_output,
            event_handler_factory=lambda started_at: VoiceTurnEventPrinter(
                debug_output=debug_output,
                turn_started_at=started_at,
            ),
            result_handler=lambda result: print_turn_result(
                result,
                config,
                debug_output=debug_output,
                verbose_context=args.verbose_context,
            ),
        )
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        _print_timings_when_available(debug_output, results)
        return 130
    except TimeoutError as error:
        print(f"[timeout] {error}", file=sys.stderr)
        _print_timings_when_available(debug_output, results)
        return 2
    except TranscriptionRuntimeError as error:
        print(f"[transcription] {error}", file=sys.stderr)
        return 3
    except MachineStateError as error:
        print(f"[machine-state] {error}", file=sys.stderr)
        return 4
    except MemoryReadinessError as error:
        print(f"[memory] {error}", file=sys.stderr)
        return 5
    except Exception as error:
        print(f"[error] {type(error).__name__}: {error}", file=sys.stderr)
        _print_timings_when_available(debug_output, results)
        return 1

    if debug_output and args.turns != 1:
        print_timing_summary(results)
    return 0


def _configure_baml_logging(debug_output: bool) -> None:
    if not debug_output:
        os.environ["BAML_LOG"] = "OFF"


async def _prepared_voice_pipeline_config(
    args: argparse.Namespace,
) -> VoicePipelineConfig:
    if not args.no_task_choice:
        await _ensure_voice_memory_context(args)
    return voice_pipeline_config(args)


async def _ensure_voice_memory_context(args: argparse.Namespace) -> None:
    if (args.session_id is None) != (args.conversation_id is None):
        print(
            "[error] --session-id and --conversation-id must be provided together",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if args.session_id is not None and args.conversation_id is not None:
        await _validate_voice_memory_context(args.session_id, args.conversation_id)
        return

    database = await open_memory_database()
    try:
        await require_memory_ready(database, require_task_catalog=True)
        session = await database.sessions.create(
            Session(name=_timestamped_name("Voice session")),
            tags=("voice",),
        )
        args.session_id = session.id
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


async def _validate_voice_memory_context(
    session_id: str,
    conversation_id: str,
) -> None:
    database = await open_memory_database()
    try:
        await require_memory_ready(database, require_task_catalog=True)
        try:
            session = await database.sessions.get(session_id, mark_read=False)
            expected_conversation_id = memory_node_record_id(conversation_id)
        except ValueError as error:
            print(f"[error] {error}", file=sys.stderr)
            raise SystemExit(2) from error
        if session is None:
            print(f"[error] session does not exist: {session_id}", file=sys.stderr)
            raise SystemExit(2)
        conversations = await database.sessions.conversations_for(
            session_id,
            mark_read=False,
        )
        if not any(item.id == expected_conversation_id for item in conversations):
            print(
                "[error] conversation is not attached to session: "
                f"{conversation_id} session_id={session_id}",
                file=sys.stderr,
            )
            raise SystemExit(2)
    finally:
        await database.close()


def _print_timings_when_available(debug_output: bool, results) -> None:
    if debug_output and results:
        print_timing_summary(results)


def _timestamped_name(prefix: str) -> str:
    return f"{prefix} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
