"""Structured task compatibility, identity, conflicts and shared operations."""

import asyncio
import io
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ai_pm_agent import config, git_repo, task_cli, task_model, task_service, todos_repo
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


@pytest.mark.parametrize("pushed", [True, False])
def test_bridge_noop_status_retries_failed_publication(monkeypatch, capsys, pushed):
    root = Path(config.TODOS_REPO_PATH)
    before = seed(root)
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    command = Mock(
        side_effect=[(True, "")] * 4
        + [(False, "offline")]
        + [(True, "")] * 3
        + [(False, "nothing to commit, working tree clean"), (pushed, "retry outcome")]
    )
    monkeypatch.setattr(git_repo, "run", command)
    payload = {
        "action": "update",
        "project": "app",
        "id": before["items"][0]["id"],
        "revision": before["revision"],
        "status": "in_progress",
    }
    monkeypatch.setattr(task_cli.sys, "stdin", io.StringIO(json.dumps(payload)))
    assert task_cli.main() == 0
    first = json.loads(capsys.readouterr().out)
    assert first["ok"] and first["published"] is False
    assert "Saved locally" in first["warning"]
    content = (root / "projects/app/todo.md").read_bytes()

    payload["revision"] = first["workspace"]["revision"]
    monkeypatch.setattr(task_cli.sys, "stdin", io.StringIO(json.dumps(payload)))
    assert task_cli.main() == 0
    retry = json.loads(capsys.readouterr().out)
    assert retry["ok"] and retry["published"] is pushed
    assert retry["warning"] == (None if pushed else first["warning"])
    assert retry["message"] == ("Pushed to ai-todos." if pushed else "retry outcome")
    assert retry["workspace"] == first["workspace"]
    assert (root / "projects/app/todo.md").read_bytes() == content
    assert command.call_count == 10
    assert (
        sum(
            args.args[0] == ["git", "push", "origin", "main"]
            for args in command.call_args_list
        )
        == 2
    )


def test_project_selection_is_independent_state():
    result = task_service.execute({"action": "select", "project": "new-project"})
    assert todos_repo.active_project() == "new-project"
    assert result["workspace"]["items"] == []


@pytest.fixture
def bridge(monkeypatch, capsys):
    def request(payload):
        monkeypatch.setattr(task_cli.sys, "stdin", io.StringIO(json.dumps(payload)))
        assert task_cli.main() == 0
        return json.loads(capsys.readouterr().out)

    return request


@pytest.fixture(params=["duplicate", "invalid"])
def malformed_project(request):
    path = Path(config.TODOS_REPO_PATH) / "projects/a/todo.md"
    path.parent.mkdir(parents=True)
    first_id = "a" * 32
    second_id = first_id if request.param == "duplicate" else "invalid"
    path.write_text(
        f'- [ ] first <!-- pm-task:{{"id":"{first_id}"}} -->\n'
        f'- [X] second <!-- pm-task:{{"id":"{second_id}"}} -->\n'
        "- [ ] legacy open\n- [x] legacy done\n"
    )
    return path


def test_bridge_valid_project_ignores_malformed_summary(
    malformed_project, bridge, monkeypatch
):
    original = malformed_project.read_bytes()
    root = Path(config.TODOS_REPO_PATH)
    path = root / "projects/b/todo.md"
    path.parent.mkdir(parents=True)
    path.write_text("- [ ] legacy open\n- [X] legacy done\n")
    empty = root / "projects/empty/todo.md"
    empty.parent.mkdir(parents=True)
    empty.write_text("")
    todos_repo.set_active_project("a")
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    publish = Mock(return_value=(True, ""))
    monkeypatch.setattr(todos_repo, "commit_and_push", publish)

    result = bridge({"action": "read", "project": "b"})
    assert result["ok"] is True
    state = result["workspace"]
    assert state["active_project"] == "a"
    assert state["projects"] == [
        {"name": "a", "open": 2, "done": 2},
        {"name": "b", "open": 1, "done": 1},
        {"name": "empty", "open": 0, "done": 0},
    ]
    assert [item["status"] for item in state["items"]] == ["open", "done"]
    stale_revision = state["revision"]
    item_id = "b" * 32
    for action, fields, counts in [
        ("add", {"text": "new"}, (2, 1)),
        ("update", {"text": "updated", "status": "done"}, (1, 2)),
        ("delete", {}, (1, 1)),
    ]:
        result = bridge(
            {
                "action": action,
                "project": "b",
                "id": item_id,
                "revision": state["revision"],
                **fields,
            }
        )
        assert result["ok"] is True
        assert result["published"] is True
        state = result["workspace"]
        assert state["active_project"] == "a"
        assert state["project"] == "b"
        assert state["projects"][1] == {
            "name": "b",
            "open": counts[0],
            "done": counts[1],
        }
        matching = [item for item in state["items"] if item["id"] == item_id]
        if action == "delete":
            assert matching == []
        else:
            assert matching[0]["text"] == fields["text"]

    before = path.read_bytes()
    result = bridge(
        {
            "action": "update",
            "project": "b",
            "id": state["items"][0]["id"],
            "revision": stale_revision,
            "status": "done",
        }
    )
    assert result["ok"] is False
    assert result["conflict"] is True
    assert path.read_bytes() == before
    assert publish.call_count == 3
    assert malformed_project.read_bytes() == original
    assert todos_repo.active_project() == "a"

    selected = bridge({"action": "select", "project": "b"})
    assert selected["ok"] is True
    assert selected["workspace"]["active_project"] == "b"
    assert bridge({"action": "read"})["workspace"]["project"] == "b"
    empty_result = bridge({"action": "read", "project": "empty"})
    assert empty_result["ok"] is True
    assert empty_result["workspace"]["items"] == []
    assert todos_repo.active_project() == "b"


@pytest.mark.parametrize("action", ["read", "select", "add", "update", "delete"])
def test_bridge_malformed_selected_project_fails_without_editing(
    malformed_project, bridge, monkeypatch, action
):
    original = malformed_project.read_bytes()
    monkeypatch.setattr(todos_repo, "ensure_repo", lambda: (True, ""))
    publish = Mock()
    monkeypatch.setattr(todos_repo, "commit_and_push", publish)
    result = bridge(
        {
            "action": action,
            "project": "a",
            "id": "b" * 32,
            "text": "new",
            "revision": task_model.revision(original.decode()),
        }
    )
    assert result == {"ok": False, "error": "Invalid or duplicate task ID"}
    assert malformed_project.read_bytes() == original
    publish.assert_not_called()


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
