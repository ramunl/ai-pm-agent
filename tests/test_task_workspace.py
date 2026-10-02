"""Structured task compatibility, identity, conflicts and shared operations."""

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ai_pm_agent import config, task_model, task_service, todos_repo
from ai_pm_agent.bot.task_edits import edit_task


def seed(root, text="- [ ] first\n- [ ] second\n- [x] old\n"):
    path = root / "projects" / "app" / "todo.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Notes\n\n" + text + "\nUnrelated paragraph\n")
    return task_model.load(root, "app")


def test_legacy_identity_survives_completion_and_deletion(tmp_path):
    state = seed(tmp_path)
    ids = [item["id"] for item in state["items"]]
    after = task_model.mutate(
        tmp_path,
        "app",
        "update",
        {
            "id": ids[0],
            "revision": state["revision"],
            "status": "done",
            "priority": "high",
        },
    )
    assert [item["id"] for item in after["items"]] == ids
    after = task_model.mutate(
        tmp_path, "app", "delete", {"id": ids[1], "revision": after["revision"]}
    )
    assert [item["id"] for item in after["items"]] == [ids[0], ids[2]]
    assert "Unrelated paragraph" in (tmp_path / "projects/app/todo.md").read_text()
    assert after["items"][0]["priority"] == "high"


def test_duplicate_text_has_distinct_ids(tmp_path):
    state = seed(tmp_path, "- [ ] same\n- [ ] same\n")
    assert len({i["id"] for i in state["items"]}) == 2


def test_stale_revision_cannot_change_another_task(tmp_path):
    before = seed(tmp_path)
    task_model.mutate(
        tmp_path,
        "app",
        "delete",
        {"id": before["items"][0]["id"], "revision": before["revision"]},
    )
    with pytest.raises(task_model.TaskConflictError):
        task_model.mutate(
            tmp_path,
            "app",
            "update",
            {
                "id": before["items"][1]["id"],
                "revision": before["revision"],
                "status": "done",
            },
        )
    assert task_model.load(tmp_path, "app")["items"][0]["status"] == "open"


def test_add_retries_do_not_duplicate_items(tmp_path):
    payload = {
        "id": uuid.uuid4().hex,
        "text": "new",
        "revision": task_model.revision(""),
    }
    task_model.mutate(tmp_path, "app", "add", payload)
    task_model.mutate(tmp_path, "app", "add", payload)
    assert len(task_model.load(tmp_path, "app")["items"]) == 1


@pytest.mark.parametrize("project", ["../escape", "/tmp/a", ".", "a/b", "", "a\\b"])
def test_rejects_unsafe_projects(tmp_path, project):
    with pytest.raises(ValueError):
        task_model.project_path(tmp_path, project)


def test_rejects_project_symlink_outside_repo(tmp_path):
    root = tmp_path / "repo"
    (root / "projects").mkdir(parents=True)
    (root / "projects" / "app").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        task_model.project_path(root, "app")


@pytest.mark.parametrize(
    "fields",
    [
        {"text": "\n- [ ] injected"},
        {"priority": "urgent"},
        {"status": "running"},
        {"text": "<!-- pm-task:{} -->"},
    ],
)
def test_invalid_edit_leaves_file_untouched(tmp_path, fields):
    before = seed(tmp_path)
    with pytest.raises(ValueError):
        task_model.mutate(
            tmp_path,
            "app",
            "update",
            {"id": before["items"][0]["id"], "revision": before["revision"], **fields},
        )
    assert task_model.load(tmp_path, "app") == before


def test_bot_completion_preserves_priority_and_hides_metadata(monkeypatch):
    root = Path(config.TODOS_REPO_PATH)
    state = seed(root)
    task_model.mutate(
        root,
        "app",
        "update",
        {
            "id": state["items"][0]["id"],
            "revision": state["revision"],
            "priority": "high",
            "status": "blocked",
        },
    )
    todos_repo.complete_todo("app", 1)
    assert task_model.load(root, "app")["items"][0]["priority"] == "high"
    assert "pm-task" not in todos_repo.numbered_todos("app")[1]
    assert todos_repo.todo_summary("app") == {"open": ["second"], "done": 2}


def test_failed_sync_never_mutates(monkeypatch):
    before = seed(Path(config.TODOS_REPO_PATH))
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (False, "pull failed"))
    result = task_service.execute(
        {
            "action": "delete",
            "project": "app",
            "id": before["items"][0]["id"],
            "revision": before["revision"],
        }
    )
    assert result["ok"] is False
    assert task_model.load(Path(config.TODOS_REPO_PATH), "app") == before


def test_failed_push_reports_saved_workspace(monkeypatch):
    before = seed(Path(config.TODOS_REPO_PATH))
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    monkeypatch.setattr(todos_repo, "commit_and_push", lambda _: (False, "push failed"))
    result = task_service.execute(
        {
            "action": "update",
            "project": "app",
            "id": before["items"][0]["id"],
            "revision": before["revision"],
            "status": "in_progress",
        }
    )
    assert result["ok"] and not result["published"]
    assert "Saved locally" in result["warning"]
    assert result["workspace"]["items"][0]["status"] == "in_progress"


def test_project_selection_is_independent_state():
    result = task_service.execute({"action": "select", "project": "new-project"})
    assert todos_repo.active_project() == "new-project"
    assert result["workspace"]["items"] == []


def test_telegram_priority_uses_shared_operations(chat, monkeypatch):
    seed(Path(config.TODOS_REPO_PATH))
    todos_repo.set_active_project("app")
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    monkeypatch.setattr(todos_repo, "commit_and_push", lambda _: (True, ""))
    chat.message.text = "/todo_priority 2 high"
    asyncio.run(edit_task(chat, SimpleNamespace(args=["2", "high"])))
    assert (
        task_model.load(Path(config.TODOS_REPO_PATH), "app")["items"][1]["priority"]
        == "high"
    )


def test_unauthorized_edit_does_not_acquire_lock(chat, monkeypatch):
    from ai_pm_agent import task_lock

    chat.message.chat_id += 1
    acquire = Mock(side_effect=AssertionError("must not lock"))
    monkeypatch.setattr(task_lock.Path, "open", acquire)
    asyncio.run(edit_task(chat, SimpleNamespace(args=[])))
    acquire.assert_not_called()


def test_cli_reports_conflict_without_traceback(monkeypatch, capsys):
    import io

    from ai_pm_agent import task_cli

    seed(Path(config.TODOS_REPO_PATH))
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    monkeypatch.setattr(
        task_cli.sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "action": "delete",
                    "project": "app",
                    "revision": "old",
                    "id": "a" * 32,
                }
            )
        ),
    )
    assert task_cli.main() == 0
    assert json.loads(capsys.readouterr().out)["conflict"] is True


def test_transaction_lock_refuses_a_second_process_handle():
    from ai_pm_agent import task_lock

    with task_lock.acquire():
        with pytest.raises(ValueError, match="Another PM operation"):
            task_lock.acquire(timeout=0.01)


def test_sync_retries_pending_publication(monkeypatch):
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    retry = Mock(return_value=(False, "offline"))
    monkeypatch.setattr(todos_repo, "retry_publish", retry)
    result = task_service.execute({"action": "sync"})
    retry.assert_called_once()
    assert not result["published"]
    assert "still saved" in result["warning"]
