"""Focused tests for Telegram bot command registration."""

import os
import unittest
from unittest.mock import AsyncMock

os.environ.setdefault("PM_TELEGRAM_BOT_TOKEN", "123456:test-token")
os.environ.setdefault("YOUR_CHAT_ID", "123456")

from ai_pm_agent.telegram_bot import BOT_COMMANDS, register_commands


class RegisterCommandsTest(unittest.IsolatedAsyncioTestCase):
    async def test_registers_every_command_for_telegram_hints(self) -> None:
        app = AsyncMock()

        await register_commands(app)

        app.bot.set_my_commands.assert_awaited_once_with(BOT_COMMANDS)
        self.assertEqual(
            ["start", "files", "rules", "addrule", "removerule", "sync"],
            [command.command for command in BOT_COMMANDS],
        )


if __name__ == "__main__":
    unittest.main()
