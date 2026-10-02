"""Handle project TODO selection and edits."""

from functools import partial

from telegram import Update
from telegram.ext import ContextTypes

from ai_pm_agent import todos_repo
from ai_pm_agent.bot.repository_actions import publish_mutation, require_repository
from ai_pm_agent.bot.transport import is_authorized, reply
from ai_pm_agent.task_lock import serialized


async def _require_active_project(update: Update) -> str | None:
    """Return the PM-owned active project or explain how to select one."""
    project = todos_repo.active_project()
    if project is not None:
        return project
    await reply(
        update,
        "No active todo project. Set one with /todo_use <project>, "
        "then /todo_add works against it.",
    )
    return None


@serialized
async def todo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the active TODO project, independently of the coding agent."""
    if not is_authorized(update):
        return
    project = todos_repo.active_project()
    text = (
        f"📌 Active todo project: {project}"
        if project is not None
        else "No active todo project yet. Set one with /todo_use <project>."
    )
    await reply(update, text)


@serialized
async def todo_use(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Persist the PM agent's selected TODO project."""
    if not is_authorized(update):
        return
    if not context.args:
        await reply(update, "Usage: /todo_use <project>")
        return
    project = context.args[0]
    try:
        todos_repo.set_active_project(project)
    except ValueError as error:
        await reply(update, str(error))
        return
    await reply(
        update,
        f"📌 Active todo project is now: {project}\n"
        "This is separate from the coding agent's project.",
    )


@serialized
async def todo_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List projects with TODO files and mark the active selection."""
    if not is_authorized(update):
        return
    if not await require_repository(update, todos_repo.ensure_repo):
        return
    names = todos_repo.list_projects()
    if not names:
        await reply(
            update, "No todo lists yet. /todo_use <project> then /todo_add <text>."
        )
        return
    active = todos_repo.active_project()
    lines = ["🗂 Projects with todo lists:"]
    for name in names:
        marker = " (active)" if name == active else ""
        lines.append(f"- {name}{marker}")
    await reply(update, "\n".join(lines))


@serialized
async def todo_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the active project's open TODO items after synchronization."""
    if not is_authorized(update):
        return
    project = await _require_active_project(update)
    if project is None or not await require_repository(update, todos_repo.ensure_repo):
        return
    ok, body = todos_repo.numbered_todos(project)
    await reply(update, f"📋 {project} todos:\n{body}")


@serialized
async def todo_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add and publish an item in the active project's TODO list."""
    if not is_authorized(update):
        return
    project = await _require_active_project(update)
    if project is None:
        return
    text = " ".join(context.args).strip()
    if not text:
        await reply(update, "Usage: /todo_add <text>")
        return
    if not await require_repository(update, todos_repo.ensure_repo):
        return
    await publish_mutation(
        update,
        todos_repo.add_todo(project, text),
        partial(todos_repo.commit_and_push, f"todos: add to {project}"),
    )


@serialized
async def todo_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mark a numbered open TODO done and publish the change."""
    if not is_authorized(update):
        return
    project = await _require_active_project(update)
    if project is None:
        return
    if not context.args or not context.args[0].isdigit():
        await reply(update, "Usage: /todo_done <number>  (see /todo_list)")
        return
    if not await require_repository(update, todos_repo.ensure_repo):
        return
    await publish_mutation(
        update,
        todos_repo.complete_todo(project, int(context.args[0])),
        partial(todos_repo.commit_and_push, f"todos: complete in {project}"),
    )
