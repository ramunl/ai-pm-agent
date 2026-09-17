"""Synchronize and publish the PM agent's markdown repositories."""

import logging
from dataclasses import dataclass
from pathlib import Path

from ai_pm_agent.shell import run

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RepositoryConfig:
    """Describe a markdown repository and its commit identity."""

    path: str
    url: str
    label: str
    author_name: str
    author_email: str


def ensure_repo(repository: RepositoryConfig) -> tuple[bool, str]:
    """Clone a missing repository or fast-forward its main branch."""
    root = Path(repository.path)
    if (root / ".git").exists():
        result = run(
            ["git", "pull", "--ff-only", "origin", "main"], cwd=repository.path
        )
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        result = run(["git", "clone", repository.url, repository.path])
    if not result[0]:
        logger.error("Could not synchronize %s: %s", repository.label, result[1])
    return result


def commit_and_push(repository: RepositoryConfig, message: str) -> tuple[bool, str]:
    """Commit markdown edits and publish them to main, stopping on Git errors."""
    preparation = [
        ["git", "config", "user.name", repository.author_name],
        ["git", "config", "user.email", repository.author_email],
        ["git", "add", "-A"],
    ]
    for command in preparation:
        ok, output = run(command, cwd=repository.path)
        if not ok:
            return False, output
    ok, output = run(["git", "commit", "-m", message], cwd=repository.path)
    if not ok:
        if "nothing to commit" in output:
            return True, "No changes to push."
        return False, output
    ok, output = run(["git", "push", "origin", "main"], cwd=repository.path)
    if not ok:
        return False, output
    return True, f"Pushed to {repository.label}."
