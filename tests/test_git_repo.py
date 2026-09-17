"""Verify synchronization and publication of markdown repositories."""

from unittest.mock import Mock, call

import pytest

from ai_pm_agent import git_repo


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


def test_nothing_to_commit_does_not_push(repository, monkeypatch):
    command = Mock(
        side_effect=[(True, "")] * 3
        + [(False, "nothing to commit, working tree clean")]
    )
    monkeypatch.setattr(git_repo, "run", command)
    assert git_repo.commit_and_push(repository, "edit") == (True, "No changes to push.")
    assert command.call_count == 4


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
