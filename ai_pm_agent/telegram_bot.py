"""Wire Telegram commands and startup registration."""

from __future__ import annotations

import logging

from telegram.ext import Application, CommandHandler

from ai_pm_agent import config
from ai_pm_agent.bot.catalog import BOT_COMMANDS
from ai_pm_agent.bot.help import start
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


def build_application() -> Application:
    """Build the application with command handlers and startup hooks."""
    app = (
        Application.builder()
        .token(config.PM_TELEGRAM_BOT_TOKEN)
        .post_init(register_commands)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
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
