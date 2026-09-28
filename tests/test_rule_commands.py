"""Verify rule command validation, synchronization, and publication results."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ai_pm_agent import config, rules_repo, telegram_bot, todos_repo
from ai_pm_agent.bot import rules


@pytest.mark.parametrize(
    "name",
    [
        "start",
        "files",
        "rules",
        "addrule",
        "removerule",
        "sync",
        "todo",
        "todo_use",
        "todo_list",
        "todo_add",
        "todo_done",
        "todo_projects",
    ],
)
def test_unauthorized_commands_do_not_read_or_edit_repositories(
    name, chat, monkeypatch
):
    def unexpected(*args, **kwargs):
        raise AssertionError("Unauthorized command touched a repository")

    for repository in (rules_repo, todos_repo):
        monkeypatch.setattr(repository, "ensure_repo", unexpected)
        monkeypatch.setattr(repository, "commit_and_push", unexpected)
    monkeypatch.setattr(rules_repo, "add_rule", unexpected)
    monkeypatch.setattr(todos_repo, "active_project", unexpected)
    monkeypatch.setattr(todos_repo, "set_active_project", unexpected)
    chat.message.chat_id = config.AUTHORIZED_CHAT_ID + 1

    asyncio.run(
        getattr(telegram_bot, name)(
            chat, SimpleNamespace(args=["python", "|", "a rule"])
        )
    )

    chat.message.reply_text.assert_not_awaited()


@pytest.mark.parametrize(
    "args,expected",
    [
        ([], "Missing separator"),
        (["python", "rule"], "Missing separator"),
        (["python", "|"], "Both file and rule text"),
        (["|", "text"], "Both file and rule text"),
    ],
)
def test_invalid_add_rule_arguments_do_not_sync_or_edit(
    args, expected, chat, monkeypatch
):
    sync, add = Mock(), Mock()
    monkeypatch.setattr(rules_repo, "ensure_repo", sync)
    monkeypatch.setattr(rules_repo, "add_rule", add)
    asyncio.run(rules.addrule(chat, SimpleNamespace(args=args)))
    sync.assert_not_called()
    add.assert_not_called()
    assert expected in chat.message.reply_text.await_args.args[0]


def test_failed_sync_stops_rule_mutation(chat, monkeypatch):
    monkeypatch.setattr(
        rules_repo, "ensure_repo", Mock(return_value=(False, "not fast-forward"))
    )
    add = Mock()
    monkeypatch.setattr(rules_repo, "add_rule", add)
    asyncio.run(
        rules.addrule(chat, SimpleNamespace(args=["python", "|", "Use dataclasses"]))
    )
    add.assert_not_called()
    assert "Sync problem" in chat.message.reply_text.await_args.args[0]


@pytest.mark.parametrize("pushed,prefix", [(True, "✅"), (False, "⚠️")])
def test_add_rule_reply_reflects_push_outcome(chat, monkeypatch, pushed, prefix):
    events = []
    monkeypatch.setattr(
        rules_repo, "ensure_repo", lambda: (events.append("sync") or True, "synced")
    )
    monkeypatch.setattr(
        rules_repo,
        "add_rule",
        lambda *args: (events.append("edit") or True, "Added to global/python.md"),
    )
    publish = Mock(
        side_effect=lambda *args: (events.append("publish") or pushed, "push result")
    )
    monkeypatch.setattr(rules_repo, "commit_and_push", publish)
    asyncio.run(
        rules.addrule(chat, SimpleNamespace(args=["python", "|", "Use dataclasses"]))
    )
    assert events == ["sync", "edit", "publish"]
    assert chat.message.reply_text.await_args.args[0].startswith(prefix)
    publish.assert_called_once_with("rules: add to python")


def test_failed_rule_removal_is_not_published(chat, monkeypatch):
    monkeypatch.setattr(rules_repo, "ensure_repo", Mock(return_value=(True, "")))
    monkeypatch.setattr(
        rules_repo, "remove_rule", Mock(return_value=(False, "No rule #9"))
    )
    publish = Mock()
    monkeypatch.setattr(rules_repo, "commit_and_push", publish)
    asyncio.run(rules.removerule(chat, SimpleNamespace(args=["python", "9"])))
    publish.assert_not_called()
    assert "⚠️ No rule #9" in chat.message.reply_text.await_args.args[0]
