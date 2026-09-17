"""Show the PM agent command reference."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ai_pm_agent.bot.transport import is_authorized, reply


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the available commands and their usage."""
    if not is_authorized(update):
        return
    await reply(
        update,
        "📐 PM Agent — rules management\n\n"
        "/files - list all rule files\n"
        "/rules <file> - show rules in a file\n"
        "/addrule <file> | <rule text> - add a rule\n"
        "/removerule <file> <number> - remove a rule\n"
        "/sync - pull latest rules from GitHub\n\n"
        "TODO lists (per project, independent of the coding agent):\n"
        "/todo - show the active todo project\n"
        "/todo_use <project> - switch active todo project\n"
        "/todo_list - show todos for the active project\n"
        "/todo_add <text> - add a todo\n"
        "/todo_done <number> - mark a todo done\n"
        "/todo_projects - list projects with todo lists\n\n"
        "Example:\n"
        "/addrule kotlin | Prefer sealed classes for UI state",
    )
