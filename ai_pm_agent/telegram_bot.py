"""Wire Telegram commands and startup registration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from telegram.ext import Application, CommandHandler

from ai_pm_agent import config
from ai_pm_agent.bot.catalog import BOT_COMMANDS
from ai_pm_agent.bot.help import core, start, version
from ai_pm_agent.bot.rules import addrule, files, removerule, rules, sync
from ai_pm_agent.bot.todos import (
    todo,
    todo_add,
    todo_done,
    todo_list,
    todo_projects,
    todo_use,
)

logger = logging.getLogger(__name__)


async def register_commands(app: Application) -> None:
    """Register commands so Telegram shows suggestions after typing `/`."""
    await app.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Registered %d Telegram command hints", len(BOT_COMMANDS))


_publisher_task: asyncio.Task | None = None


async def on_startup(app: Application) -> None:
    """Register command hints, then start publishing the dashboard snapshot.

    Kept separate from register_commands so tests of the command hints never
    start a publisher that writes to the real snapshot path.
    """
    global _publisher_task
    await register_commands(app)
    if _publisher_task is None or _publisher_task.done():
        from .snapshot import publish_forever

        _publisher_task = asyncio.get_running_loop().create_task(
            publish_forever(Path(config.PM_SNAPSHOT_FILE))
        )


async def on_shutdown(app: Application) -> None:
    """Stop publishing on a clean shutdown."""
    global _publisher_task
    if _publisher_task is not None:
        _publisher_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _publisher_task
        _publisher_task = None


def build_application() -> Application:
    """Build the application with command handlers and startup hooks."""
    app = (
        Application.builder()
        .token(config.PM_TELEGRAM_BOT_TOKEN)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("core", core))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(CommandHandler("sync", sync))
    app.add_handler(CommandHandler("files", files))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("addrule", addrule))
    app.add_handler(CommandHandler("removerule", removerule))
    app.add_handler(CommandHandler("todo", todo))
    app.add_handler(CommandHandler("todo_use", todo_use))
    app.add_handler(CommandHandler("todo_list", todo_list))
    app.add_handler(CommandHandler("todo_add", todo_add))
    app.add_handler(CommandHandler("todo_done", todo_done))
    app.add_handler(CommandHandler("todo_projects", todo_projects))
    return app
