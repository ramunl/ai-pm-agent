"""Manage the ai-rules repository: sync, read, edit, commit, push.

A "rule file" is a markdown file anywhere in the repo (e.g. global/kotlin.md,
projects/channel-cast/architecture.md). A "rule" is a single markdown bullet
line ('- ...') within such a file. Rules are referenced by the file's stem
name (e.g. 'kotlin', 'architecture') and a 1-based index within that file.
"""

import logging
import os
from pathlib import Path

from . import config
from .shell import run

logger = logging.getLogger(__name__)


def ensure_repo() -> tuple[bool, str]:
    """Clone the rules repo if missing, otherwise pull the latest."""
    repo_exists = os.path.isdir(os.path.join(config.RULES_REPO_PATH, ".git"))
    if repo_exists:
        ok, output = run(
            ["git", "pull", "--ff-only", "origin", "main"],
            cwd=config.RULES_REPO_PATH,
        )
        if not ok:
            logger.error("Could not pull rules repo: %s", output)
        return ok, output

    parent = os.path.dirname(config.RULES_REPO_PATH)
    Path(parent).mkdir(parents=True, exist_ok=True)
    ok, output = run(
        ["git", "clone", config.RULES_REPO_URL, config.RULES_REPO_PATH]
    )
    if not ok:
        logger.error("Could not clone rules repo: %s", output)
    return ok, output


def _rule_files() -> list[Path]:
    """All markdown files in the repo, excluding the top-level README."""
    root = Path(config.RULES_REPO_PATH)
    files = sorted(
        path
        for path in root.rglob("*.md")
        if path.name.lower() != "readme.md"
        and ".git" not in path.parts
    )
    return files


def list_files() -> list[str]:
    """Return rule file stem names, relative for disambiguation."""
    names = []
    for path in _rule_files():
        rel = path.relative_to(config.RULES_REPO_PATH)
        names.append(str(rel))
    return names


def _resolve_file(name: str) -> Path | None:
    """Find a rule file by stem, file name, or relative path."""
    candidates = _rule_files()
    wanted = name.removesuffix(".md").lower()
    for path in candidates:
        rel = str(path.relative_to(config.RULES_REPO_PATH)).lower()
        matches = (
            path.stem.lower() == wanted
            or path.name.lower() == name.lower()
            or rel == name.lower()
            or rel.removesuffix(".md") == wanted
        )
        if matches:
            return path
    return None


def read_rules(name: str) -> tuple[bool, str]:
    """Return the full markdown content of a rule file."""
    path = _resolve_file(name)
    found = path is not None
    if found:
        return True, path.read_text(encoding="utf-8")
    logger.info("Rule file not found for name: %s", name)
    return False, f"No rule file matching '{name}'."


def _bullet_lines(text: str) -> list[int]:
    """Indices of lines that are markdown bullets within the text."""
    indices = []
    for i, line in enumerate(text.splitlines()):
        is_bullet = line.lstrip().startswith("- ")
        if is_bullet:
            indices.append(i)
    return indices


def numbered_rules(name: str) -> tuple[bool, str]:
    """Return the file's rules as a numbered list (bullets only)."""
    ok, content = read_rules(name)
    if ok:
        lines = content.splitlines()
        bullets = _bullet_lines(content)
        has_rules = len(bullets) > 0
        if has_rules:
            numbered = []
            for number, line_index in enumerate(bullets, start=1):
                rule_text = lines[line_index].lstrip()[2:].strip()
                numbered.append(f"{number}. {rule_text}")
            return True, "\n".join(numbered)
        return True, "(no rules in this file yet)"
    return False, content


def add_rule(name: str, rule_text: str) -> tuple[bool, str]:
    """Append a bullet rule to a file, creating the file if needed."""
    path = _resolve_file(name)
    is_new_file = path is None
    if is_new_file:
        # New file goes under global/ by default.
        path = Path(config.RULES_REPO_PATH) / "global" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        header = f"# {name} rules\n\n"
        path.write_text(header, encoding="utf-8")
        logger.info("Created new rule file: %s", path)

    existing = path.read_text(encoding="utf-8")
    needs_newline = existing and not existing.endswith("\n")
    separator = "\n" if needs_newline else ""
    path.write_text(
        existing + separator + f"- {rule_text}\n", encoding="utf-8"
    )
    rel = path.relative_to(config.RULES_REPO_PATH)
    return True, f"Added to {rel}"


def remove_rule(name: str, number: int) -> tuple[bool, str]:
    """Remove the Nth bullet (1-based) from a rule file."""
    ok, content = read_rules(name)
    if ok:
        lines = content.splitlines()
        bullets = _bullet_lines(content)
        in_range = 1 <= number <= len(bullets)
        if in_range:
            target = bullets[number - 1]
            removed_text = lines[target].lstrip()[2:].strip()
            del lines[target]
            path = _resolve_file(name)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True, f"Removed: {removed_text}"
        logger.info("Rule number %s out of range for %s", number, name)
        return False, f"No rule #{number} in '{name}'."
    return False, content


def commit_and_push(message: str) -> tuple[bool, str]:
    """Stage everything, commit with identity, and push to main."""
    run(["git", "config", "user.name", config.GIT_AUTHOR_NAME],
        cwd=config.RULES_REPO_PATH)
    run(["git", "config", "user.email", config.GIT_AUTHOR_EMAIL],
        cwd=config.RULES_REPO_PATH)

    run(["git", "add", "-A"], cwd=config.RULES_REPO_PATH)

    ok_commit, commit_out = run(
        ["git", "commit", "-m", message], cwd=config.RULES_REPO_PATH
    )
    nothing_to_commit = (not ok_commit) and "nothing to commit" in commit_out
    if nothing_to_commit:
        return True, "No changes to push."
    if not ok_commit:
        return False, commit_out

    ok_push, push_out = run(
        ["git", "push", "origin", "main"], cwd=config.RULES_REPO_PATH
    )
    if not ok_push:
        return False, push_out
    return True, "Pushed to ai-rules."
