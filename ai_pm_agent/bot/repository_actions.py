"""Report repository synchronization and publication outcomes to Telegram."""

import asyncio
from collections.abc import Callable
from typing import TypeVar

from telegram import Update

from ai_pm_agent.bot.transport import reply

RepositoryResult = tuple[bool, str]
_Result = TypeVar("_Result")


async def run_repository(
    operation: Callable[..., _Result], *args: object, **kwargs: object
) -> _Result:
    """Run blocking work without letting cancellation outlive the caller's lock."""
    worker = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
    cancelled = False
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            if not cancelled:
                raise
    if cancelled:
        # Retrieve any worker exception before propagating the cancellation.
        worker.exception()
        raise asyncio.CancelledError
    return worker.result()


async def require_repository(
    update: Update, synchronize: Callable[[], RepositoryResult]
) -> bool:
    """Synchronize a repository and report a failure before any file is edited."""
    ok, output = await run_repository(synchronize)
    if not ok:
        await reply(update, f"⚠️ Sync problem\n{output}")
    return ok


async def publish_mutation(
    update: Update,
    mutate: Callable[[], RepositoryResult],
    publish: Callable[[], RepositoryResult],
) -> None:
    """Publish a successful local edit and distinguish Git failures from success."""
    ok, message = await run_repository(mutate)
    if not ok:
        await reply(update, f"⚠️ {message}")
        return
    pushed, output = await run_repository(publish)
    prefix = "✅" if pushed else "⚠️"
    await reply(update, f"{prefix} {message}\n{output}")
