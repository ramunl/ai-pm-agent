"""Authorize owner messages and send bounded replies."""

from __future__ import annotations

import logging

from telegram import Update

from ai_pm_agent import config

logger = logging.getLogger(__name__)


def is_authorized(update: Update) -> bool:
    """Check the owner chat and log unauthorized messages."""
    is_authorized_chat = (
        update.message is not None
        and update.message.chat_id == config.AUTHORIZED_CHAT_ID
    )
    if not is_authorized_chat:
        logger.warning(
            "Ignored message from unauthorized chat: %s",
            update.message.chat_id if update.message else "unknown",
        )
    return is_authorized_chat


async def reply(update: Update, text: str) -> None:
    """Send a plain-text reply within the configured message limit."""
    is_too_long = len(text) > config.TELEGRAM_MESSAGE_LIMIT
    if is_too_long:
        suffix = "\n... (truncated)"
        text = text[: config.TELEGRAM_MESSAGE_LIMIT - len(suffix)] + suffix
    await update.message.reply_text(text)
