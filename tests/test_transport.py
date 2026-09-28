"""Verify PM reply truncation fits the configured message limit."""

import asyncio

from ai_pm_agent import config
from ai_pm_agent.bot.transport import reply


def test_truncation_marker_is_included_in_the_message_budget(chat):
    asyncio.run(reply(chat, "x" * (config.TELEGRAM_MESSAGE_LIMIT + 1)))
    message = chat.message.reply_text.await_args.args[0]
    assert len(message) == config.TELEGRAM_MESSAGE_LIMIT
    assert message.endswith("\n... (truncated)")
