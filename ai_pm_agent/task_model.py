"""Backward-compatible Markdown tasks with stable identity and revision checks."""

import hashlib
import json
import os
import re
import tempfile
import uuid
from pathlib import Path

STATUSES = ("open", "in_progress", "blocked", "done")
PRIORITIES = ("high", "normal", "low")
ITEM = re.compile(r"^(\s*)- \[([ xX])\] (.*)$")
META = re.compile(r"\s*<!-- pm-task:(\{.*\}) -->$")


class TaskConflictError(ValueError):
    """The displayed task list is older than the stored version."""


def project_path(root: Path, project: str) -> Path:
    """Validate a project identifier and prevent paths escaping the repository."""
    if not isinstance(project, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", project
    ):
        raise ValueError(
            "Project names use letters, numbers, dots, underscores or hyphens"
        )
    base = root.resolve()
    path = base / "projects" / project / "todo.md"
    if not path.resolve().is_relative_to(base):
        raise ValueError("Project path leaves the TODO repository")
    return path


def revision(content: str) -> str:
    """Return a revision token for conflict detection, including empty lists."""
    return hashlib.sha256(content.encode()).hexdigest()


def parse_items(content: str, project: str) -> list[dict]:
    """Read both plain checkbox lines and structured tasks without changing files."""
    items = []
    ids = set()
    for index, line in enumerate(content.splitlines()):
        match = ITEM.match(line)
        if not match:
            continue
        indent, checked, text = match.groups()
        meta_match = META.search(text)
        metadata = {}
        if meta_match:
            metadata = json.loads(meta_match[1])
            if not isinstance(metadata, dict):
                raise ValueError("Invalid task metadata")
            text = text[: meta_match.start()].rstrip()
        legacy_id = uuid.uuid5(uuid.NAMESPACE_URL, f"pm:{project}:{index}:{text}").hex
        item_id = metadata.get("id", legacy_id)
        status = metadata.get("status", "done" if checked.lower() == "x" else "open")
        # A manual Markdown checkbox edit remains authoritative for completion.
        if checked.lower() == "x":
            status = "done"
        elif status == "done":
            status = "open"
        priority = metadata.get("priority", "normal")
        if (
            not isinstance(item_id, str)
            or not re.fullmatch(r"[a-f0-9]{32}", item_id)
            or item_id in ids
        ):
            raise ValueError("Invalid or duplicate task ID")
        if status not in STATUSES or priority not in PRIORITIES:
            raise ValueError("Invalid task status or priority")
        ids.add(item_id)
        items.append(
            {
                "id": item_id,
                "text": text,
                "status": status,
                "priority": priority,
                "line": index,
                "indent": indent,
            }
        )
    return items


def load(root: Path, project: str) -> dict:
    """Read a complete project workspace, with done tasks and revision token."""
    path = project_path(root, project)
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    items = parse_items(content, project)
    return {
        "project": project,
        "revision": revision(content),
        "items": [
            {k: v for k, v in item.items() if k not in ("line", "indent")}
            for item in items
        ],
    }


def atomic_write(path: Path, content: str) -> None:
    """Replace a file atomically so snapshots cannot observe half-written data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".pm-task-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _render(item: dict) -> str:
    metadata = {key: item[key] for key in ("id", "status", "priority")}
    marker = "x" if item["status"] == "done" else " "
    encoded = json.dumps(metadata, separators=(",", ":"))
    prefix = f"{item.get('indent', '')}- [{marker}] {item['text']}"
    return f"{prefix} <!-- pm-task:{encoded} -->"


def _validate_fields(data: dict) -> None:
    text = data.get("text")
    if text is not None and (
        not isinstance(text, str)
        or not text.strip()
        or len(text) > 10000
        or "\n" in text
        or "\r" in text
        or "<!-- pm-task:" in text
    ):
        raise ValueError(
            "Todo text must be one non-empty line, at most 10,000 characters"
        )
    if "status" in data and data["status"] not in STATUSES:
        raise ValueError("Unknown task status")
    if "priority" in data and data["priority"] not in PRIORITIES:
        raise ValueError("Unknown task priority")


def mutate(root: Path, project: str, action: str, data: dict) -> dict:
    """Apply one revision-checked mutation; retain all unrelated Markdown lines."""
    path = project_path(root, project)
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    items = parse_items(content, project)
    _validate_fields(data)
    if action not in ("add", "update", "delete"):
        raise ValueError("Unknown TODO action")
    # Retry-safe add: the caller reuses its generated ID after an uncertain answer.
    if action == "add" and any(item["id"] == data.get("id") for item in items):
        existing = next(item for item in items if item["id"] == data["id"])
        if existing["text"] != data.get("text", "").strip():
            raise TaskConflictError("Task ID already exists with different content")
        return load(root, project)
    if data.get("revision") != revision(content):
        raise TaskConflictError(
            "This list changed. Refresh and review before saving again."
        )
    lines = content.splitlines()
    target = next((item for item in items if item["id"] == data.get("id")), None)
    if action == "add":
        if "text" not in data:
            raise ValueError("Todo text is required")
        item_id = data.get("id", uuid.uuid4().hex)
        if not isinstance(item_id, str) or not re.fullmatch(r"[a-f0-9]{32}", item_id):
            raise ValueError("Invalid task ID")
        target = {
            "id": item_id,
            "text": data["text"].strip(),
            "status": data.get("status", "open"),
            "priority": data.get("priority", "normal"),
        }
    elif target is None:
        raise TaskConflictError("This todo no longer exists. Refresh the list.")
    elif action == "update":
        for key in ("text", "status", "priority"):
            if key in data:
                target[key] = data[key].strip() if key == "text" else data[key]
    # Persist identities of legacy items together before their positions can shift.
    for item in items:
        lines[item["line"]] = _render(item)
    if action == "delete":
        del lines[target["line"]]
    elif action == "add":
        if not lines:
            lines = [f"# {project} — TODO", ""]
        lines.append(_render(target))
    atomic_write(path, "\n".join(lines) + "\n")
    return load(root, project)
