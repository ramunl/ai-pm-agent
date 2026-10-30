"""Manage the ai-rules repository: sync, read, edit, commit, push.

A "rule file" is a markdown file anywhere in the repo (e.g. global/kotlin.md,
projects/channel-cast/architecture.md). A "rule" is a single markdown bullet
line ('- ...') within such a file. Rules are referenced by exact relative path
or unambiguous shorthand and a 1-based index within that file.
"""

import logging
import re
from pathlib import Path

from ai_pm_agent import config, git_repo

logger = logging.getLogger(__name__)


def validate_rule_name(name: str) -> tuple[bool, str]:
    """Accept simple names or safe relative selectors for existing rule files."""
    if all(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", part)
        for part in name.split("/")
    ):
        return True, ""
    return False, (
        "Invalid rule name. Use relative paths with 1–80 ASCII letters, digits, "
        "underscores, dots or hyphens per component, starting with a letter "
        "or digit; absolute paths and traversal are not allowed."
    )


def _contained_path(path: Path) -> Path:
    """Resolve a target and reject paths outside the resolved repository."""
    root = Path(config.RULES_REPO_PATH).resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Rule path is outside the rules repository.")
    return resolved


def ensure_repo() -> tuple[bool, str]:
    """Synchronize the repository before reading or editing markdown."""
    return git_repo.ensure_repo(_repository())


def _rule_files() -> list[Path]:
    """All markdown files in the repo, excluding the top-level README."""
    root = Path(config.RULES_REPO_PATH)
    files = sorted(
        path
        for path in root.rglob("*.md")
        if path.name.lower() != "readme.md" and ".git" not in path.parts
    )
    return files


def list_files() -> list[str]:
    """Return rule file stem names, relative for disambiguation."""
    names = []
    for path in _rule_files():
        rel = path.relative_to(config.RULES_REPO_PATH)
        names.append(str(rel))
    return names


def rule_counts() -> list[dict]:
    """Each rule file (relative path) with how many rules it holds."""
    counts = []
    for path in _rule_files():
        try:
            text = _contained_path(path).read_text(encoding="utf-8")
        except (OSError, RuntimeError, ValueError) as error:
            logger.warning("Could not count rules in %s: %s", path, error)
            continue
        counts.append(
            {
                "file": str(path.relative_to(config.RULES_REPO_PATH)),
                "count": len(_bullet_lines(text)),
            }
        )
    return counts


def _resolve_file(name: str) -> Path | None:
    """Find a rule file by stem, file name, or relative path."""
    ok, message = validate_rule_name(name)
    if not ok:
        raise ValueError(message)
    candidates = _rule_files()
    root = Path(config.RULES_REPO_PATH)
    for path in candidates:
        if path.relative_to(root).as_posix() == name:
            return path
    wanted = name.lower().removesuffix(".md")
    matches = [
        path
        for path in candidates
        if path.stem.lower() == wanted
        or path.name.lower() == name.lower()
        or path.relative_to(root).as_posix().lower().removesuffix(".md") == wanted
    ]
    if len(matches) > 1:
        paths = sorted(path.relative_to(root).as_posix() for path in matches)
        raise ValueError(
            f"Ambiguous rule file '{name}'. Use an exact relative path:\n"
            + "\n".join(paths)
        )
    return matches[0] if matches else None


def read_rules(name: str) -> tuple[bool, str]:
    """Return the full markdown content of a rule file."""
    try:
        path = _resolve_file(name)
        if path is not None:
            return True, _contained_path(path).read_text(encoding="utf-8")
    except (OSError, RuntimeError, ValueError) as error:
        return False, f"Cannot read rule file: {error}"
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
    ok, message = validate_rule_name(name)
    if not ok:
        return False, message
    try:
        path = _resolve_file(name)
        is_new_file = path is None
        if is_new_file:
            if "/" in name:
                return False, (
                    f"No rule file matching '{name}'. "
                    "New global files require a simple name without a path."
                )
            path = Path(config.RULES_REPO_PATH) / "global" / f"{name}.md"
        path = _contained_path(path)
        if is_new_file:
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = f"# {name} rules\n\n"
        else:
            existing = path.read_text(encoding="utf-8")
        needs_newline = existing and not existing.endswith("\n")
        separator = "\n" if needs_newline else ""
        path.write_text(existing + separator + f"- {rule_text}\n", encoding="utf-8")
    except (OSError, RuntimeError, ValueError) as error:
        return False, f"Cannot add rule: {error}"
    rel = path.relative_to(Path(config.RULES_REPO_PATH).resolve())
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
            try:
                path = _resolve_file(name)
                if path is None:
                    return False, f"No rule file matching '{name}'."
                _contained_path(path).write_text(
                    "\n".join(lines) + "\n", encoding="utf-8"
                )
            except (OSError, RuntimeError, ValueError) as error:
                return False, f"Cannot remove rule: {error}"
            return True, f"Removed: {removed_text}"
        logger.info("Rule number %s out of range for %s", number, name)
        return False, f"No rule #{number} in '{name}'."
    return False, content


def commit_and_push(message: str) -> tuple[bool, str]:
    """Publish markdown edits using the configured repository identity."""
    return git_repo.commit_and_push(_repository(), message)


def _repository() -> git_repo.RepositoryConfig:
    """Read repository settings at call time to keep configuration changes visible."""
    return git_repo.RepositoryConfig(
        path=config.RULES_REPO_PATH,
        url=config.RULES_REPO_URL,
        label="ai-rules",
        author_name=config.GIT_AUTHOR_NAME,
        author_email=config.GIT_AUTHOR_EMAIL,
    )
