"""Serialize TODO transactions across Telegram and dashboard CLI processes."""

import asyncio
import fcntl
import functools
import time
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from ai_pm_agent import config
from ai_pm_agent.bot.transport import is_authorized


def acquire(timeout: float = 10) -> TextIO:
    """Acquire the shared repository lock; the caller closes the returned handle."""
    path = Path(config.TODOS_STATE_FILE).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a")
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except BlockingIOError:
            if time.monotonic() >= deadline:
                handle.close()
                raise ValueError("Another PM operation is running. Try again shortly.")
            time.sleep(0.05)


def serialized(handler: Callable) -> Callable:
    """Wrap a Telegram handler in the same transaction lock used by the CLI."""

    @functools.wraps(handler)
    async def wrapped(*args: object, **kwargs: object) -> object:
        if not is_authorized(args[0]):
            return await handler(*args, **kwargs)
        # Nonblocking attempts avoid leaving a lock acquired by a cancelled thread.
        path = Path(config.TODOS_STATE_FILE).with_suffix(".lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(0.05)
            return await handler(*args, **kwargs)

    return wrapped
