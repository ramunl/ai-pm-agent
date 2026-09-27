"""Show help, runtime versions, and shared-core status."""

import asyncio
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from ai_agent_common import CoreCommand, get_runtime_version, render_help
from ai_pm_agent.bot.catalog import COMMANDS
from ai_pm_agent.bot.transport import is_authorized, reply

ROOT_DIR = Path(__file__).resolve().parents[2]
_CORE_COMMAND = CoreCommand(
    submodule_dir=ROOT_DIR / "ai_agent_common",
    superproject_dir=ROOT_DIR,
    submodule_path="ai_agent_common",
    agent_name="ai-pm-agent",
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the PM command catalog."""
    if not is_authorized(update):
        return
    await reply(
        update,
        render_help(
            "PM Agent",
            COMMANDS,
            intro="Rules and per-project TODO management.",
        ),
    )


async def version(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Report the PM agent version using the shared core implementation."""
    if not is_authorized(update):
        return
    text = get_runtime_version("ai-pm-agent", ROOT_DIR)
    await reply(update, f"{text}\n{_CORE_COMMAND.short_line()}")


async def core(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Report this bot's pinned shared-core version."""
    if not is_authorized(update):
        return
    text = await asyncio.to_thread(_CORE_COMMAND.status_text)
    await reply(update, text)
