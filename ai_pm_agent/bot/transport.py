"""Authorize owner messages and send bounded replies."""

from __future__ import annotations

import logging

from telegram import Update

from ai_agent_common import is_authorized as shared_is_authorized
from ai_pm_agent import config

logger = logging.getLogger(__name__)


def is_authorized(update: Update) -> bool:
    """Check the owner chat and log unauthorized messages."""
    authorized = shared_is_authorized(update, config.AUTHORIZED_CHAT_ID)
    if not authorized:
        logger.warning(
            "Ignored message from unauthorized chat: %s",
            getattr(getattr(update, "effective_chat", None), "id", "unknown"),
        )
    return authorized


async def reply(update: Update, text: str) -> None:
    """Send a plain-text reply within the configured message limit."""
    is_too_long = len(text) > config.TELEGRAM_MESSAGE_LIMIT
    if is_too_long:
        suffix = "\n... (truncated)"
        text = text[: config.TELEGRAM_MESSAGE_LIMIT - len(suffix)] + suffix
    await update.message.reply_text(text)
