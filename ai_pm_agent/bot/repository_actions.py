"""Report repository synchronization and publication outcomes to Telegram."""

from collections.abc import Callable

from telegram import Update

from ai_pm_agent.bot.transport import reply

RepositoryResult = tuple[bool, str]


async def require_repository(
    update: Update, synchronize: Callable[[], RepositoryResult]
) -> bool:
    """Synchronize a repository and report a failure before any file is edited."""
    ok, output = synchronize()
    if not ok:
        await reply(update, f"⚠️ Sync problem\n{output}")
    return ok


async def publish_mutation(
    update: Update,
    result: RepositoryResult,
    publish: Callable[[], RepositoryResult],
) -> None:
    """Publish a successful local edit and distinguish Git failures from success."""
    ok, message = result
    if not ok:
        await reply(update, f"⚠️ {message}")
        return
    pushed, output = publish()
    prefix = "✅" if pushed else "⚠️"
    await reply(update, f"{prefix} {message}\n{output}")
