from __future__ import annotations

import asyncio
from collections.abc import Callable
from threading import Thread
from typing import TypeVar


T = TypeVar("T")


async def run_in_daemon_thread(func: Callable[..., T], *args) -> T:
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def complete_with_result(result: T) -> None:
        if not future.cancelled():
            future.set_result(result)

    def complete_with_error(error: BaseException) -> None:
        if not future.cancelled():
            future.set_exception(error)

    def run() -> None:
        try:
            result = func(*args)
        except BaseException as exc:
            loop.call_soon_threadsafe(complete_with_error, exc)
            return
        loop.call_soon_threadsafe(complete_with_result, result)

    Thread(target=run, daemon=True).start()
    return await future
