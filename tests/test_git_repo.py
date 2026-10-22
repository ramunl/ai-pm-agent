"""Verify synchronization and publication of markdown repositories."""

from unittest.mock import Mock, call

import pytest

from ai_pm_agent import config, git_repo, rules_repo, todos_repo


@pytest.fixture
def repository(tmp_path):
    return git_repo.RepositoryConfig(
        str(tmp_path / "rules"),
        "git@example.test:rules.git",
        "ai-rules",
        "Bot",
        "bot@example.test",
    )


def test_missing_repository_is_cloned(repository, monkeypatch):
    command = Mock(return_value=(True, "cloned"))
    monkeypatch.setattr(git_repo, "run", command)
    assert git_repo.ensure_repo(repository) == (True, "cloned")
    command.assert_called_once_with(["git", "clone", repository.url, repository.path])


@pytest.mark.parametrize("git_file", [False, True])
def test_existing_checkout_only_fast_forwards_main(repository, monkeypatch, git_file):
    from pathlib import Path

    root = Path(repository.path)
    root.mkdir()
    if git_file:
        (root / ".git").write_text("gitdir: ../repo.git")
    else:
        (root / ".git").mkdir()
    command = Mock(return_value=(True, "updated"))
    monkeypatch.setattr(git_repo, "run", command)
    assert git_repo.ensure_repo(repository)[0]
    command.assert_called_once_with(
        ["git", "pull", "--ff-only", "origin", "main"], cwd=repository.path
    )


@pytest.mark.parametrize("failed_step", range(5))
def test_failed_git_step_stops_publication(repository, monkeypatch, failed_step):
    responses = [(True, "ok")] * failed_step + [(False, "git failed")]
    command = Mock(side_effect=responses)
    monkeypatch.setattr(git_repo, "run", command)
    assert git_repo.commit_and_push(repository, "rules: edit") == (False, "git failed")
    assert command.call_count == failed_step + 1


@pytest.mark.parametrize(
    "caller,label", [(rules_repo, "ai-rules"), (todos_repo, "ai-todos")]
)
@pytest.mark.parametrize("pushed", [True, False])
def test_nothing_to_commit_returns_push_outcome(
    tmp_path, monkeypatch, caller, label, pushed
):
    path = str(tmp_path / label)
    monkeypatch.setattr(config, "RULES_REPO_PATH", path)
    monkeypatch.setattr(config, "TODOS_REPO_PATH", path)
    command = Mock(
        side_effect=[(True, "")] * 3
        + [(False, "nothing to commit, working tree clean")]
        + [(pushed, "push rejected" if not pushed else "Everything up-to-date")]
    )
    monkeypatch.setattr(git_repo, "run", command)
    assert caller.commit_and_push("edit") == (
        pushed,
        f"Pushed to {label}." if pushed else "push rejected",
    )
    assert command.call_count == 5
    command.assert_called_with(["git", "push", "origin", "main"], cwd=path)


def test_successful_publication_sets_identity_and_pushes_main(repository, monkeypatch):
    command = Mock(return_value=(True, "ok"))
    monkeypatch.setattr(git_repo, "run", command)
    assert git_repo.commit_and_push(repository, "rules: edit") == (
        True,
        "Pushed to ai-rules.",
    )
    assert command.call_args_list == [
        call(["git", "config", "user.name", "Bot"], cwd=repository.path),
        call(["git", "config", "user.email", "bot@example.test"], cwd=repository.path),
        call(["git", "add", "-A"], cwd=repository.path),
        call(["git", "commit", "-m", "rules: edit"], cwd=repository.path),
        call(["git", "push", "origin", "main"], cwd=repository.path),
    ]
