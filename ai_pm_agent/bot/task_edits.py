"""Telegram adapters for structured TODO edits shared with the dashboard."""

from telegram import Update
from telegram.ext import ContextTypes

from ai_pm_agent import task_service, todos_repo
from ai_pm_agent.bot.transport import is_authorized, reply
from ai_pm_agent.task_lock import serialized


@serialized
async def edit_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Edit/remove open items by number; reopen completed items by their stable ID."""
    if not is_authorized(update):
        return
    command = update.message.text.split()[0].split("@")[0].lstrip("/")
    project = todos_repo.active_project()
    if not project or not context.args:
        await reply(
            update,
            "Select a project with /todo_use, then supply an item number "
            "(or ID for /todo_reopen).",
        )
        return
    try:
        synced, message = todos_repo.ensure_repo()
        if not synced:
            await reply(update, "TODO sync failed: " + message)
            return
        state = task_service.workspace(project)
        items = [item for item in state["items"] if item["status"] != "done"]
        selector = context.args[0]
        if command == "todo_reopen":
            item = next((i for i in state["items"] if i["id"] == selector), None)
        else:
            number = int(selector)
            item = items[number - 1] if 1 <= number <= len(items) else None
        if item is None:
            raise ValueError("Item not found. Refresh /todo_list first.")
        payload = {
            "project": project,
            "revision": state["revision"],
            "id": item["id"],
            "action": "update",
        }
        value = " ".join(context.args[1:]).strip().lstrip("|").strip()
        if command == "todo_remove":
            payload["action"] = "delete"
        elif command == "todo_edit":
            payload["text"] = value
        elif command == "todo_priority":
            payload["priority"] = value
        elif command == "todo_status":
            payload["status"] = value
        elif command == "todo_reopen":
            payload["status"] = "open"
        result = task_service.execute(payload)
        await reply(
            update,
            result.get("error")
            or result.get("warning")
            or "Todo updated and pushed to GitHub.",
        )
    except ValueError as error:
        await reply(update, str(error))


@serialized
async def todo_done_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List completed item IDs so Telegram users can reopen them."""
    if not is_authorized(update):
        return
    project = todos_repo.active_project()
    if not project:
        await reply(update, "Select a project with /todo_use first.")
        return
    synced, message = todos_repo.ensure_repo()
    if not synced:
        await reply(update, "TODO sync failed: " + message)
        return
    items = task_service.workspace(project)["items"]
    lines = [
        f"{item['id']} · {item['text']}" for item in items if item["status"] == "done"
    ]
    await reply(update, f"Completed · {project}\n" + ("\n".join(lines) or "None"))
