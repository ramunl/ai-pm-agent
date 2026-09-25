"""Publish the PM agent's read model to a file for the dashboard service.

The dashboard runs as its own service so it keeps working when this bot is
down. It never talks to this process; it reads the file written here, which is
the whole contract between the two. Todo and rule parsing stays in
todos_repo / rules_repo, so the dashboard never needs to know their formats.

Written when the content changes and at least every HEARTBEAT_SECONDS, so the
dashboard can tell "nothing changed" apart from "the PM agent stopped".
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path

from ai_agent_common import CoreCommand, get_runtime_version

from . import rules_repo, todos_repo

logger = logging.getLogger(__name__)

SNAPSHOT_FORMAT = 1
INTERVAL_SECONDS = 3.0
HEARTBEAT_SECONDS = 30.0
# Enough for a phone screen; the full list stays one /todo_list away.
MAX_OPEN_ITEMS = 50

ROOT_DIR = Path(__file__).resolve().parent.parent


def versions() -> dict:
    """Agent and core version. Only a deploy changes them, and it restarts us."""
    core = CoreCommand(
        submodule_dir=ROOT_DIR / "ai_agent_common",
        superproject_dir=ROOT_DIR,
        submodule_path="ai_agent_common",
        agent_name="ai-pm-agent",
    )
    return {
        "version": get_runtime_version("ai-pm-agent", ROOT_DIR),
        "core": core.short_line(),
    }


def build_content(version_info: dict) -> dict:
    """Everything the PM window shows, minus the timestamps."""
    active = todos_repo.active_project()
    projects = []
    for name in todos_repo.list_projects():
        summary = todos_repo.todo_summary(name)
        projects.append({"name": name, "open": len(summary["open"]), "done": summary["done"]})
    todos = None
    if active:
        summary = todos_repo.todo_summary(active)
        todos = {
            "project": active,
            "open": summary["open"][:MAX_OPEN_ITEMS],
            "open_count": len(summary["open"]),
            "done": summary["done"],
        }
    return {
        "format": SNAPSHOT_FORMAT,
        "active_project": active,
        "todos": todos,
        "projects": projects,
        "rules": rules_repo.rule_counts(),
        **version_info,
    }


def write_json_atomic(path: Path, payload: dict) -> bool:
    """Temp file + rename, owner-only; log and return False on error."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
    except OSError as error:
        logger.error("Could not write %s: %s", path, error)
        return False
    return True


class SnapshotPublisher:
    """Writes the snapshot on change and on heartbeat; never raises."""

    def __init__(self, path: Path, heartbeat: float = HEARTBEAT_SECONDS) -> None:
        self.path = Path(path)
        self.heartbeat = heartbeat
        self._last_content: dict | None = None
        self._last_written = 0.0

    def publish(self, content: dict, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        changed = content != self._last_content
        due = current - self._last_written >= self.heartbeat
        if not (changed or due):
            return False
        payload = {**content, "updated_at": current, "pid": os.getpid()}
        if write_json_atomic(self.path, payload):
            self._last_content = content
            self._last_written = current
            return True
        return False


async def publish_forever(path: Path, interval: float = INTERVAL_SECONDS) -> None:
    """Run until cancelled. A failing tick is logged and retried on the next."""
    publisher = SnapshotPublisher(path)
    try:
        version_info = await asyncio.to_thread(versions)
    except Exception as error:  # versions are nice-to-have
        logger.warning("Snapshot: could not read versions: %s", error)
        version_info = {"version": "unknown", "core": "unknown"}
    while True:
        try:
            content = await asyncio.to_thread(build_content, version_info)
            publisher.publish(content)
        except Exception as error:
            logger.warning("Snapshot publish failed (will retry): %s", error)
        await asyncio.sleep(interval)
