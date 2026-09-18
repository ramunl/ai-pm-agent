"""Focused tests for Telegram bot command registration."""

import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("PM_TELEGRAM_BOT_TOKEN", "123456:test-token")
os.environ.setdefault("YOUR_CHAT_ID", "123456")

from ai_pm_agent.telegram_bot import (
    BOT_COMMANDS,
    build_application,
    register_commands,
    version,
)


class RegisterCommandsTest(unittest.IsolatedAsyncioTestCase):
    async def test_registers_every_command_for_telegram_hints(self) -> None:
        app = AsyncMock()

        await register_commands(app)

        app.bot.set_my_commands.assert_awaited_once_with(BOT_COMMANDS)
        self.assertEqual(
            [
                "help",
                "version",
                "start",
                "files",
                "rules",
                "addrule",
                "removerule",
                "sync",
                "core",
                "todo",
                "todo_use",
                "todo_list",
                "todo_add",
                "todo_done",
                "todo_projects",
            ],
            [command.command for command in BOT_COMMANDS],
        )

    def test_catalog_matches_registered_command_handlers(self) -> None:
        application = build_application()
        handler_commands = {
            command
            for handlers in application.handlers.values()
            for handler in handlers
            for command in getattr(handler, "commands", ())
        }

        self.assertEqual(
            {command.command for command in BOT_COMMANDS},
            handler_commands,
        )

    async def test_version_uses_shared_runtime_report(self) -> None:
        message = SimpleNamespace(chat_id=123456, reply_text=AsyncMock())
        update = SimpleNamespace(message=message, effective_chat=None)
        context = SimpleNamespace()

        with patch(
            "ai_pm_agent.telegram_bot.get_runtime_version",
            return_value="ai-pm-agent v1\nbranch: main\ncommit: abc123",
        ) as runtime_version, patch(
            "ai_pm_agent.telegram_bot._CORE_COMMAND.short_line",
            return_value="core: v1.1",
        ):
            await version(update, context)

        runtime_version.assert_called_once()
        message.reply_text.assert_awaited_once_with(
            "ai-pm-agent v1\nbranch: main\ncommit: abc123\ncore: v1.1"
        )


if __name__ == "__main__":
    unittest.main()
