from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
import sys
import time
from threading import Event

from reframe_agent_host.voice.daemon_threads import run_in_daemon_thread
from reframe_agent_host.voice.pipeline import VoiceTurnPipeline
from reframe_agent_host.voice.types import (
    CaptureStreamEvent,
    VoicePipelineEventHandler,
    VoiceTurnControl,
    VoiceTurnResult,
)


EventHandlerFactory = Callable[[float], VoicePipelineEventHandler]
TurnResultHandler = Callable[[VoiceTurnResult], None]


async def run_voice_turn_loop(
    *,
    turns: int,
    pipeline: VoiceTurnPipeline,
    results: list[VoiceTurnResult],
    debug_output: bool,
    event_handler_factory: EventHandlerFactory,
    result_handler: TurnResultHandler,
) -> None:
    prepare_started_at = time.perf_counter()
    model_prepare_seconds = pipeline.prepare(event_handler_factory(prepare_started_at))
    tasks: set[asyncio.Task] = set()
    try:
        if debug_output:
            print("[turn 1] starting", file=sys.stderr)

        await _capture_and_start_speculative_session(
            pipeline=pipeline,
            max_turns=turns,
            model_prepare_seconds=model_prepare_seconds,
            on_event=event_handler_factory(prepare_started_at),
            results=results,
            tasks=tasks,
            result_handler=result_handler,
        )
    except BaseException:
        await _cancel_background_turns(tasks)
        raise
    else:
        if tasks:
            await asyncio.gather(*tasks)


async def _capture_and_start_speculative_session(
    *,
    pipeline: VoiceTurnPipeline,
    max_turns: int,
    model_prepare_seconds: float,
    on_event: VoicePipelineEventHandler,
    results: list[VoiceTurnResult],
    tasks: set[asyncio.Task],
    result_handler: TurnResultHandler,
) -> None:
    queue: asyncio.Queue[CaptureStreamEvent] = asyncio.Queue()
    stop_event = Event()
    loop = asyncio.get_running_loop()

    def emit_capture_event(event: CaptureStreamEvent) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    worker = asyncio.create_task(
        run_in_daemon_thread(
            pipeline.capture_speculative_session,
            on_event,
            emit_capture_event,
            stop_event,
            max_turns,
        )
    )
    active_turn_id: int | None = None
    active_capture = None
    active_control: VoiceTurnControl | None = None
    active_task: asyncio.Task | None = None
    first_flow = True

    try:
        while True:
            _raise_completed_turn_errors(tasks)
            event = await _next_capture_event(queue, worker)
            if event is None:
                return

            if event.kind == "endpoint":
                if event.capture is None:
                    continue
                if active_control is not None:
                    active_control.cancel()
                if active_task is not None:
                    active_task.cancel()

                active_turn_id = event.turn_id
                active_capture = event.capture
                active_control = VoiceTurnControl()
                turn_started_at = time.perf_counter()
                turn_prepare_seconds = model_prepare_seconds if first_flow else 0.0
                first_flow = False
                active_task = asyncio.create_task(
                    _process_captured_voice_turn(
                        pipeline=pipeline,
                        capture=event.capture,
                        model_prepare_seconds=turn_prepare_seconds,
                        turn_started_at=turn_started_at,
                        on_event=on_event,
                        results=results,
                        result_handler=result_handler,
                        turn_control=active_control,
                    )
                )
                tasks.add(active_task)
            elif event.kind == "resumed":
                if event.turn_id == active_turn_id:
                    if active_control is not None:
                        active_control.cancel()
                    if active_task is not None:
                        active_task.cancel()
                    active_turn_id = None
                    active_capture = None
                    active_control = None
                    active_task = None
                    on_event("turn-cancelled", "speech resumed before endpoint settled")
            elif event.kind == "confirmed":
                confirmed_capture = event.capture or active_capture
                if confirmed_capture is not None:
                    pipeline.apply_capture_mode(confirmed_capture)
                if event.turn_id == active_turn_id and active_control is not None:
                    active_control.commit()
                active_turn_id = None
                active_capture = None
                active_control = None
                active_task = None
            elif event.kind == "mode_switch":
                if event.capture is None:
                    continue
                pipeline.apply_capture_mode(event.capture)
                turn_started_at = time.perf_counter()
                turn_prepare_seconds = model_prepare_seconds if first_flow else 0.0
                first_flow = False
                task = asyncio.create_task(
                    _process_captured_voice_turn(
                        pipeline=pipeline,
                        capture=event.capture,
                        model_prepare_seconds=turn_prepare_seconds,
                        turn_started_at=turn_started_at,
                        on_event=on_event,
                        results=results,
                        result_handler=result_handler,
                    )
                )
                tasks.add(task)
    except BaseException:
        stop_event.set()
        if active_control is not None:
            active_control.cancel()
        if active_task is not None:
            active_task.cancel()
        with suppress(BaseException):
            await asyncio.wait_for(asyncio.shield(worker), timeout=1.0)
        raise


async def _next_capture_event(
    queue: asyncio.Queue[CaptureStreamEvent],
    worker: asyncio.Task,
) -> CaptureStreamEvent | None:
    if not queue.empty():
        return queue.get_nowait()
    if worker.done():
        worker.result()
        return None

    get_task = asyncio.create_task(queue.get())
    try:
        done, pending = await asyncio.wait(
            {get_task, worker},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            if task is get_task:
                task.cancel()
        if get_task in done:
            return get_task.result()
        worker.result()
        if not queue.empty():
            return queue.get_nowait()
        return None
    finally:
        if not get_task.done():
            get_task.cancel()


async def _process_captured_voice_turn(
    *,
    pipeline: VoiceTurnPipeline,
    capture,
    model_prepare_seconds: float,
    turn_started_at: float,
    on_event: VoicePipelineEventHandler,
    results: list[VoiceTurnResult],
    result_handler: TurnResultHandler,
    turn_control: VoiceTurnControl | None = None,
) -> None:
    try:
        result = await pipeline.process_capture(
            capture,
            model_prepare_seconds,
            turn_started_at,
            on_event,
            turn_control=turn_control,
        )
    except asyncio.CancelledError:
        on_event("turn-cancelled", "discarded speculative voice flow")
        raise
    except Exception as error:
        on_event("turn-error", f"{type(error).__name__}: {error}")
        return
    results.append(result)
    result_handler(result)


def _raise_completed_turn_errors(tasks: set[asyncio.Task]) -> None:
    for task in tuple(tasks):
        if task.done():
            if task.cancelled():
                tasks.discard(task)
                continue
            task.result()
            tasks.discard(task)


async def _cancel_background_turns(tasks: set[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    tasks.clear()
