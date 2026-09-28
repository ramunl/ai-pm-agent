"""Verify shared help and version commands retain owner authorization."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ai_pm_agent import config
from ai_pm_agent.bot import help


def test_help_lists_every_registered_command(chat):
    asyncio.run(help.start(chat, SimpleNamespace()))
    text = chat.message.reply_text.await_args.args[0]
    for command in help.COMMANDS:
        assert f"/{command.name}" in text


@pytest.mark.parametrize("name", ["start", "version", "core"])
def test_unauthorized_help_commands_do_not_read_or_reply(name, chat, monkeypatch):
    chat.message.chat_id = config.AUTHORIZED_CHAT_ID + 1
    runtime = Mock(side_effect=AssertionError("Unauthorized version read"))
    status = Mock(side_effect=AssertionError("Unauthorized core read"))
    monkeypatch.setattr(help, "get_runtime_version", runtime)
    monkeypatch.setattr(help._CORE_COMMAND, "status_text", status)

    asyncio.run(getattr(help, name)(chat, SimpleNamespace()))

    runtime.assert_not_called()
    status.assert_not_called()
    chat.message.reply_text.assert_not_awaited()


def test_core_reports_shared_status(chat, monkeypatch):
    status = Mock(return_value="core: v1.1")
    monkeypatch.setattr(help._CORE_COMMAND, "status_text", status)

    asyncio.run(help.core(chat, SimpleNamespace()))

    status.assert_called_once_with()
    chat.message.reply_text.assert_awaited_once_with("core: v1.1")
