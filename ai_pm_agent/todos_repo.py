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
from pathlib import Path

from ai_pm_agent import config, git_repo, task_model
from ai_pm_agent.shell import run

logger = logging.getLogger(__name__)


def ensure_repo() -> tuple[bool, str]:
    """Synchronize the repository before reading or editing markdown."""
    return git_repo.ensure_repo(_repository())


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
    """Persist the PM-owned active TODO project on disk."""
    task_model.project_path(Path(config.TODOS_REPO_PATH), name)
    state = Path(config.TODOS_STATE_FILE)
    task_model.atomic_write(state, name + "\n")
    logger.info("Active todo project set to %s", name)


def list_projects() -> list[str]:
    """Project names that have a todo list in the repo."""
    projects_dir = Path(config.TODOS_REPO_PATH) / "projects"
    exists = projects_dir.is_dir()
    if exists:
        return sorted(child.name for child in projects_dir.iterdir() if child.is_dir())
    return []


# ---------------------------------------------------------------- todo files


def _todo_path(project: str) -> Path:
    return task_model.project_path(Path(config.TODOS_REPO_PATH), project)


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
    text = stripped[len("- [ ] ") :].strip()
    return task_model.META.sub("", text).rstrip()


def todo_summary(project: str) -> dict:
    """Open item texts and done count for a project; empty if no list yet."""
    path = _todo_path(project)
    if not path.is_file():
        return {"open": [], "done": 0}
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    return {
        "open": [_item_text(lines[i]) for i in _checkbox_lines(content, done=False)],
        "done": len(_checkbox_lines(content, done=True)),
    }


def numbered_todos(project: str) -> tuple[bool, str]:
    """Open items numbered, followed by a count of done items."""
    path = _todo_path(project)
    exists = path.is_file()
    if not exists:
        return True, "(no todo list yet — add one with /todo_add)"

    content = path.read_text(encoding="utf-8")
    open_lines = _checkbox_lines(content, done=False)
    done_lines = _checkbox_lines(content, done=True)

    has_open = len(open_lines) > 0
    if has_open:
        items = [
            item
            for item in task_model.parse_items(content, project)
            if item["status"] != "done"
        ]
        numbered = []
        for number, item in enumerate(items, start=1):
            labels = []
            if item["priority"] != "normal":
                labels.append(item["priority"])
            if item["status"] != "open":
                labels.append(item["status"].replace("_", " "))
            suffix = f" [{' · '.join(labels)}]" if labels else ""
            numbered.append(f"{number}. {item['text']}{suffix}")
        body = "\n".join(numbered)
    else:
        body = "(nothing open — all clear)"

    done_note = f"\n\n✅ {len(done_lines)} done" if done_lines else ""
    return True, body + done_note


def add_todo(project: str, text: str) -> tuple[bool, str]:
    """Append an open TODO item, creating the list if needed."""
    try:
        data = task_model.load(Path(config.TODOS_REPO_PATH), project)
        task_model.mutate(
            Path(config.TODOS_REPO_PATH),
            project,
            "add",
            {
                "revision": data["revision"],
                "text": text,
            },
        )
    except ValueError as error:
        return False, str(error)
    return True, f"Added to {project}"


def complete_todo(project: str, number: int) -> tuple[bool, str]:
    """Mark the Nth OPEN item (1-based) as done."""
    data = task_model.load(Path(config.TODOS_REPO_PATH), project)
    items = [item for item in data["items"] if item["status"] != "done"]
    if not 1 <= number <= len(items):
        return False, f"No open item #{number} in '{project}'."
    item = items[number - 1]
    task_model.mutate(
        Path(config.TODOS_REPO_PATH),
        project,
        "update",
        {
            "revision": data["revision"],
            "id": item["id"],
            "status": "done",
        },
    )
    return True, f"Done: {item['text']}"


def commit_and_push(message: str) -> tuple[bool, str]:
    """Publish markdown edits using the configured repository identity."""
    return git_repo.commit_and_push(_repository(), message)


def _repository() -> git_repo.RepositoryConfig:
    """Read repository settings at call time to keep configuration changes visible."""
    return git_repo.RepositoryConfig(
        path=config.TODOS_REPO_PATH,
        url=config.TODOS_REPO_URL,
        label="ai-todos",
        author_name=config.GIT_AUTHOR_NAME,
        author_email=config.GIT_AUTHOR_EMAIL,
    )


def retry_publish() -> tuple[bool, str]:
    """Push existing commits after a previous publication failure, without editing."""
    return run(["git", "push", "origin", "main"], cwd=config.TODOS_REPO_PATH)
