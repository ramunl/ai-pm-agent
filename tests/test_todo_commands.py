"""Verify active-project requirements and TODO publication failures."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ai_pm_agent import config, git_repo, task_model, task_service, todos_repo
from ai_pm_agent.bot import task_edits, todos


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


@pytest.mark.parametrize("pushed", [True, False])
def test_noop_status_reports_push_outcome(chat, monkeypatch, pushed):
    from pathlib import Path

    todos_repo.set_active_project("alpha")
    todos_repo.add_todo("alpha", "first")
    path = Path(config.TODOS_REPO_PATH) / "projects/alpha/todo.md"
    content = path.read_bytes()
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    command = Mock(
        side_effect=[(True, "")] * 3
        + [(False, "nothing to commit, working tree clean"), (pushed, "offline")]
    )
    monkeypatch.setattr(git_repo, "run", command)
    chat.message.text = "/todo_status 1 open"

    asyncio.run(task_edits.edit_task(chat, SimpleNamespace(args=["1", "open"])))

    chat.message.reply_text.assert_awaited_once_with(
        "Todo updated and pushed to GitHub."
        if pushed
        else "Saved locally; GitHub sync failed. Do not add the item again."
    )
    command.assert_called_with(
        ["git", "push", "origin", "main"], cwd=config.TODOS_REPO_PATH
    )
    assert path.read_bytes() == content


@pytest.mark.parametrize(
    "result,expected",
    [
        (
            {"published": False},
            "Todo updated locally; GitHub publication was not confirmed.",
        ),
        ({}, "Todo updated locally; GitHub publication was not confirmed."),
        ({"published": True, "warning": "warning"}, "warning"),
        ({"published": False, "error": "error", "warning": "warning"}, "error"),
    ],
)
def test_structured_edit_preserves_errors_and_requires_publication(
    chat, monkeypatch, result, expected
):
    todos_repo.set_active_project("alpha")
    todos_repo.add_todo("alpha", "first")
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    monkeypatch.setattr(task_service, "execute", lambda payload: result)
    chat.message.text = "/todo_status 1 open"
    asyncio.run(task_edits.edit_task(chat, SimpleNamespace(args=["1", "open"])))
    chat.message.reply_text.assert_awaited_once_with(expected)


@pytest.mark.parametrize("name", ["todo_done", "todo_list"])
def test_invalid_task_id_replies_without_publication(name, chat, monkeypatch):
    from pathlib import Path

    path = Path(config.TODOS_REPO_PATH) / "projects" / "alpha" / "todo.md"
    path.parent.mkdir(parents=True)
    content = '- [ ] broken <!-- pm-task:{"id":"invalid"} -->\n'
    path.write_text(content)
    monkeypatch.setattr(todos_repo, "active_project", lambda: "alpha")
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    publish = Mock()
    monkeypatch.setattr(todos_repo, "commit_and_push", publish)

    asyncio.run(getattr(todos, name)(chat, SimpleNamespace(args=["1"])))

    chat.message.reply_text.assert_awaited_once_with("Invalid or duplicate task ID")
    publish.assert_not_called()
    assert path.read_text() == content


@pytest.mark.parametrize(
    "name,operation",
    [("todo_done", "complete_todo"), ("todo_list", "numbered_todos")],
)
def test_revision_conflict_replies_without_publication(
    name, operation, chat, monkeypatch
):
    message = "This list changed. Refresh and review before saving again."
    monkeypatch.setattr(todos_repo, "active_project", lambda: "alpha")
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    monkeypatch.setattr(
        todos_repo, operation, Mock(side_effect=task_model.TaskConflictError(message))
    )
    publish = Mock()
    monkeypatch.setattr(todos_repo, "commit_and_push", publish)

    asyncio.run(getattr(todos, name)(chat, SimpleNamespace(args=["1"])))

    chat.message.reply_text.assert_awaited_once_with(message)
    publish.assert_not_called()


def test_completed_todo_publishes_and_renumbers(chat, monkeypatch):
    monkeypatch.setattr(todos_repo, "active_project", lambda: "alpha")
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    publish = Mock(return_value=(True, ""))
    monkeypatch.setattr(todos_repo, "commit_and_push", publish)
    todos_repo.add_todo("alpha", "first")
    todos_repo.add_todo("alpha", "second")

    asyncio.run(todos.todo_done(chat, SimpleNamespace(args=["1"])))

    publish.assert_called_once_with("todos: complete in alpha")
    chat.message.reply_text.assert_awaited_once_with("✅ Done: first\n")
    assert todos_repo.numbered_todos("alpha") == (True, "1. second\n\n✅ 1 done")


def test_todo_add_stamps_date_and_list_hides_metadata(chat, monkeypatch):
    from datetime import date
    from pathlib import Path

    from ai_pm_agent import config, task_model

    monkeypatch.setattr(todos_repo, "active_project", lambda: "alpha")
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    monkeypatch.setattr(todos_repo, "commit_and_push", lambda message: (True, ""))
    monkeypatch.setattr(task_model, "today", lambda: date(2026, 10, 15))
    asyncio.run(todos.todo_add(chat, SimpleNamespace(args=["write", "docs"])))
    path = Path(config.TODOS_REPO_PATH) / "projects" / "alpha" / "todo.md"
    assert '"created":"2026-10-15"' in path.read_text()
    asyncio.run(todos.todo_list(chat, SimpleNamespace(args=[])))
    listing = chat.message.reply_text.await_args.args[0]
    assert listing == "📋 alpha todos:\n1. write docs"
