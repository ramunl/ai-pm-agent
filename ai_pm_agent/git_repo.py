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


def _require_main(repository: RepositoryConfig) -> tuple[bool, str]:
    """Reject checkouts that cannot be confirmed to be on main."""
    ok, output = run(["git", "symbolic-ref", "--quiet", "HEAD"], cwd=repository.path)
    if not ok:
        return False, output or (
            f"{repository.label} must be on main; HEAD is detached or unreadable."
        )
    if output.strip() != "refs/heads/main":
        return False, (
            f"{repository.label} must be on main; HEAD points to {output.strip()}."
        )
    return True, output


def ensure_repo(repository: RepositoryConfig) -> tuple[bool, str]:
    """Clone a missing repository or fast-forward its main branch."""
    root = Path(repository.path)
    if (root / ".git").exists():
        ok, output = _require_main(repository)
        if not ok:
            logger.error("Could not synchronize %s: %s", repository.label, output)
            return False, output
        result = run(
            ["git", "pull", "--ff-only", "origin", "main"], cwd=repository.path
        )
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        result = run(
            ["git", "clone", "--branch", "main", repository.url, repository.path]
        )
    if not result[0]:
        logger.error("Could not synchronize %s: %s", repository.label, result[1])
    return result


def commit_and_push(repository: RepositoryConfig, message: str) -> tuple[bool, str]:
    """Commit markdown edits and publish them to main, stopping on Git errors."""
    ok, output = _require_main(repository)
    if not ok:
        return False, output
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
    if not ok and "nothing to commit" not in output:
        return False, output
    ok, output = run(["git", "push", "origin", "main"], cwd=repository.path)
    if not ok:
        return False, output
    return True, f"Pushed to {repository.label}."
