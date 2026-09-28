"""Verify active-project requirements and TODO publication failures."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ai_pm_agent import todos_repo
from ai_pm_agent.bot import todos


@pytest.mark.parametrize("name", ["todo_add", "todo_done", "todo_list"])
def test_no_active_project_prompts_before_repository_access(name, chat, monkeypatch):
    monkeypatch.setattr(todos_repo, "active_project", lambda: None)
    sync = Mock()
    monkeypatch.setattr(todos_repo, "ensure_repo", sync)
    asyncio.run(getattr(todos, name)(chat, SimpleNamespace(args=["1"])))
    sync.assert_not_called()
    assert "No active todo project" in chat.message.reply_text.await_args.args[0]


@pytest.mark.parametrize(
    "name,args,operation",
    [("todo_add", ["new", "task"], "add_todo"), ("todo_done", ["1"], "complete_todo")],
)
def test_failed_todo_sync_blocks_edits(name, args, operation, chat, monkeypatch):
    monkeypatch.setattr(todos_repo, "active_project", lambda: "alpha")
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (False, "sync failed"))
    edit = Mock()
    monkeypatch.setattr(todos_repo, operation, edit)
    asyncio.run(getattr(todos, name)(chat, SimpleNamespace(args=args)))
    edit.assert_not_called()
    assert "sync failed" in chat.message.reply_text.await_args.args[0]


def test_completed_todo_reports_failed_push(chat, monkeypatch):
    monkeypatch.setattr(todos_repo, "active_project", lambda: "alpha")
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    complete = Mock(return_value=(True, "Done: add tests"))
    publish = Mock(return_value=(False, "push rejected"))
    monkeypatch.setattr(todos_repo, "complete_todo", complete)
    monkeypatch.setattr(todos_repo, "commit_and_push", publish)
    asyncio.run(todos.todo_done(chat, SimpleNamespace(args=["2"])))
    complete.assert_called_once_with("alpha", 2)
    assert (
        chat.message.reply_text.await_args.args[0] == "⚠️ Done: add tests\npush rejected"
    )
