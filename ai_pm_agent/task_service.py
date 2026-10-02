"""Transport-neutral TODO operations owned by the PM agent."""

from pathlib import Path

from ai_pm_agent import config, task_model, todos_repo


def workspace(project: str | None = None) -> dict:
    """Return all items for a project and the independent PM project selection."""
    active = todos_repo.active_project()
    selected = project or active
    projects = []
    root = Path(config.TODOS_REPO_PATH)
    for name in todos_repo.list_projects():
        items = task_model.load(root, name)["items"]
        projects.append(
            {
                "name": name,
                "open": sum(i["status"] != "done" for i in items),
                "done": sum(i["status"] == "done" for i in items),
            }
        )
    result = (
        task_model.load(root, selected)
        if selected
        else {"project": None, "revision": None, "items": []}
    )
    return {**result, "active_project": active, "projects": projects}


def execute(payload: dict) -> dict:
    """Run a validated operation inside the caller's repository transaction lock."""
    action = payload.get("action", "read")
    project = payload.get("project")
    if action not in ("read", "select", "add", "update", "delete", "sync"):
        raise ValueError("Unknown PM action")
    if project is not None:
        task_model.project_path(Path(config.TODOS_REPO_PATH), project)
    if action == "read":
        return {"ok": True, "workspace": workspace(project)}
    if not project and action != "sync":
        raise ValueError("Select a project first")
    if action == "select":
        todos_repo.set_active_project(project)
        return {"ok": True, "workspace": workspace(project)}
    synchronized, message = todos_repo.ensure_repo()
    if not synchronized:
        return {"ok": False, "error": "TODO sync failed: " + message}
    if action == "sync":
        pushed, message = todos_repo.retry_publish()
        return {
            "ok": True,
            "published": pushed,
            "message": message,
            "warning": None
            if pushed
            else "GitHub sync failed. Local items are still saved.",
            "workspace": workspace(project),
        }
    data = {
        key: payload[key]
        for key in ("id", "revision", "text", "status", "priority")
        if key in payload
    }
    task_model.mutate(Path(config.TODOS_REPO_PATH), project, action, data)
    pushed, message = todos_repo.commit_and_push(f"todos: {action} in {project}")
    return {
        "ok": True,
        "published": pushed,
        "message": message,
        "warning": None
        if pushed
        else "Saved locally; GitHub sync failed. Do not add the item again.",
        "workspace": workspace(project),
    }
