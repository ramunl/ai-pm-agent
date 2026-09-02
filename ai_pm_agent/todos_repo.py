"""Manage the ai-todos repository: per-project TODO lists in markdown.

Layout mirrors ai-rules:
    projects/<project>/todo.md

Each TODO is a markdown checkbox line. Open items are "- [ ] text";
done items are "- [x] text". Items are referenced by a 1-based index over
the OPEN items in the active project's list.

The active project is state owned by THIS agent, stored in a local file. It is
deliberately independent of the coding agent's active project — the two are not
coupled, so selecting a project here never affects code changes there.
"""

import logging
import os
from pathlib import Path

from . import config
from .shell import run

logger = logging.getLogger(__name__)


def ensure_repo() -> tuple[bool, str]:
    """Clone the todos repo if missing, otherwise pull the latest."""
    repo_exists = os.path.isdir(os.path.join(config.TODOS_REPO_PATH, ".git"))
    if repo_exists:
        ok, output = run(
            ["git", "pull", "--ff-only", "origin", "main"],
            cwd=config.TODOS_REPO_PATH,
        )
        if not ok:
            logger.error("Could not pull todos repo: %s", output)
        return ok, output

    parent = os.path.dirname(config.TODOS_REPO_PATH)
    Path(parent).mkdir(parents=True, exist_ok=True)
    ok, output = run(
        ["git", "clone", config.TODOS_REPO_URL, config.TODOS_REPO_PATH]
    )
    if not ok:
        logger.error("Could not clone todos repo: %s", output)
    return ok, output


# ---------------------------------------------------------------- active project


def active_project() -> str | None:
    """The PM agent's current todo project, or None if unset."""
    state = Path(config.TODOS_STATE_FILE)
    has_state = state.is_file()
    if has_state:
        name = state.read_text(encoding="utf-8").strip()
        return name or None
    return None


def set_active_project(name: str) -> None:
    state = Path(config.TODOS_STATE_FILE)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(name.strip() + "\n", encoding="utf-8")
    logger.info("Active todo project set to %s", name)


def list_projects() -> list[str]:
    """Project names that have a todo list in the repo."""
    projects_dir = Path(config.TODOS_REPO_PATH) / "projects"
    exists = projects_dir.is_dir()
    if exists:
        return sorted(
            child.name for child in projects_dir.iterdir() if child.is_dir()
        )
    return []


# ---------------------------------------------------------------- todo files


def _todo_path(project: str) -> Path:
    return Path(config.TODOS_REPO_PATH) / "projects" / project / "todo.md"


def _checkbox_lines(text: str, done: bool) -> list[int]:
    """Line indices of checkbox items, filtered by done state."""
    marker = "- [x] " if done else "- [ ] "
    indices = []
    for i, line in enumerate(text.splitlines()):
        is_match = line.lstrip().lower().startswith(marker.lower())
        if is_match:
            indices.append(i)
    return indices


def _item_text(line: str) -> str:
    stripped = line.lstrip()
    return stripped[len("- [ ] "):].strip()


def numbered_todos(project: str) -> tuple[bool, str]:
    """Open items numbered, followed by a count of done items."""
    path = _todo_path(project)
    exists = path.is_file()
    if not exists:
        return True, "(no todo list yet — add one with /todo_add)"

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    open_lines = _checkbox_lines(content, done=False)
    done_lines = _checkbox_lines(content, done=True)

    has_open = len(open_lines) > 0
    if has_open:
        numbered = [
            f"{number}. {_item_text(lines[line_index])}"
            for number, line_index in enumerate(open_lines, start=1)
        ]
        body = "\n".join(numbered)
    else:
        body = "(nothing open — all clear)"

    done_note = f"\n\n✅ {len(done_lines)} done" if done_lines else ""
    return True, body + done_note


def add_todo(project: str, text: str) -> tuple[bool, str]:
    """Append an open TODO item, creating the list if needed."""
    path = _todo_path(project)
    is_new = not path.is_file()
    if is_new:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {project} — TODO\n\n", encoding="utf-8")
        logger.info("Created todo list: %s", path)

    existing = path.read_text(encoding="utf-8")
    needs_newline = existing and not existing.endswith("\n")
    separator = "\n" if needs_newline else ""
    path.write_text(existing + separator + f"- [ ] {text}\n", encoding="utf-8")
    return True, f"Added to {project}"


def complete_todo(project: str, number: int) -> tuple[bool, str]:
    """Mark the Nth OPEN item (1-based) as done."""
    path = _todo_path(project)
    exists = path.is_file()
    if not exists:
        return False, f"No todo list for '{project}'."

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    open_lines = _checkbox_lines(content, done=False)
    in_range = 1 <= number <= len(open_lines)
    if in_range:
        target = open_lines[number - 1]
        done_text = _item_text(lines[target])
        indent = lines[target][: len(lines[target]) - len(lines[target].lstrip())]
        lines[target] = f"{indent}- [x] {done_text}"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True, f"Done: {done_text}"
    logger.info("Todo #%s out of range for %s", number, project)
    return False, f"No open item #{number} in '{project}'."


def commit_and_push(message: str) -> tuple[bool, str]:
    """Stage everything, commit with identity, and push to main."""
    run(["git", "config", "user.name", config.GIT_AUTHOR_NAME],
        cwd=config.TODOS_REPO_PATH)
    run(["git", "config", "user.email", config.GIT_AUTHOR_EMAIL],
        cwd=config.TODOS_REPO_PATH)
    run(["git", "add", "-A"], cwd=config.TODOS_REPO_PATH)

    ok_commit, commit_out = run(
        ["git", "commit", "-m", message], cwd=config.TODOS_REPO_PATH
    )
    nothing_to_commit = (not ok_commit) and "nothing to commit" in commit_out
    if nothing_to_commit:
        return True, "No changes to push."
    if not ok_commit:
        return False, commit_out

    ok_push, push_out = run(
        ["git", "push", "origin", "main"], cwd=config.TODOS_REPO_PATH
    )
    if not ok_push:
        return False, push_out
    return True, "Pushed to ai-todos."
