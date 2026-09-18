"""Telegram bot for managing coding rules in the ai-rules repo."""

import asyncio
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from ai_agent_common import (
    Command,
    CoreCommand,
    build_command_list,
    get_runtime_version,
    is_authorized as shared_is_authorized,
    render_help,
    to_bot_commands,
)

from . import config, rules_repo, todos_repo

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
_CORE_COMMAND = CoreCommand(
    submodule_dir=ROOT_DIR / "ai_agent_common",
    superproject_dir=ROOT_DIR,
    submodule_path="ai_agent_common",
    agent_name="ai-pm-agent",
)

COMMANDS = build_command_list(
    [
        Command("start", "Show available commands"),
        Command("files", "List all rule files"),
        Command("rules", "Show rules in a file"),
        Command("addrule", "Add a rule"),
        Command("removerule", "Remove a rule"),
        Command("sync", "Pull the latest rules from GitHub"),
        Command("core", "Show the shared core version"),
        Command("todo", "Show the active todo project"),
        Command("todo_use", "Switch the active todo project"),
        Command("todo_list", "Show todos for the active project"),
        Command("todo_add", "Add a todo to the active project"),
        Command("todo_done", "Mark a todo done by number"),
        Command("todo_projects", "List projects that have todo lists"),
    ]
)
BOT_COMMANDS = tuple(to_bot_commands(COMMANDS))


def is_authorized(update: Update) -> bool:
    authorized = shared_is_authorized(update, config.AUTHORIZED_CHAT_ID)
    if not authorized:
        logger.warning(
            "Ignored message from unauthorized chat: %s",
            getattr(getattr(update, "effective_chat", None), "id", "unknown"),
        )
    return authorized


async def reply(update: Update, text: str) -> None:
    isTooLong = len(text) > config.TELEGRAM_MESSAGE_LIMIT
    if isTooLong:
        text = text[: config.TELEGRAM_MESSAGE_LIMIT] + "\n... (truncated)"
    await update.message.reply_text(text)


# ---------------------------------------------------------------- commands


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_authorized(update):
        await reply(
            update,
            render_help(
                "PM Agent",
                COMMANDS,
                intro="Rules and per-project TODO management.",
            ),
        )


async def version(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Report the PM agent version using the shared core implementation."""
    if is_authorized(update):
        text = get_runtime_version("ai-pm-agent", ROOT_DIR)
        await reply(update, f"{text}\n{_CORE_COMMAND.short_line()}")


async def core(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Report this bot's pinned shared-core version."""
    if is_authorized(update):
        text = await asyncio.to_thread(_CORE_COMMAND.status_text)
        await reply(update, text)


async def sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_authorized(update):
        ok, output = rules_repo.ensure_repo()
        prefix = "✅ Synced" if ok else "⚠️ Sync problem"
        await reply(update, f"{prefix}\n{output}")


async def files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_authorized(update):
        rules_repo.ensure_repo()
        names = rules_repo.list_files()
        has_files = len(names) > 0
        if has_files:
            await reply(update, "🗂 Rule files:\n" + "\n".join(names))
        else:
            await reply(update, "No rule files yet. Add one with /addrule.")


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_authorized(update):
        rules_repo.ensure_repo()
        hasArg = bool(context.args)
        if hasArg:
            name = context.args[0]
            ok, body = rules_repo.numbered_rules(name)
            header = f"📋 {name}:\n" if ok else ""
            await reply(update, header + body)
        else:
            await reply(update, "Usage: /rules <file>  (see /files)")


async def addrule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_authorized(update):
        raw = " ".join(context.args)
        hasSeparator = "|" in raw
        if hasSeparator:
            file_part, _, rule_part = raw.partition("|")
            name = file_part.strip()
            rule_text = rule_part.strip()
            isComplete = bool(name) and bool(rule_text)
            if isComplete:
                ok, msg = rules_repo.add_rule(name, rule_text)
                if ok:
                    pushed_ok, push_msg = rules_repo.commit_and_push(
                        f"rules: add to {name}"
                    )
                    await reply(update, f"✅ {msg}\n{push_msg}")
                else:
                    await reply(update, f"⚠️ {msg}")
            else:
                await reply(
                    update,
                    "Both file and rule text are required.\n"
                    "Usage: /addrule <file> | <rule text>",
                )
        else:
            await reply(
                update,
                "Missing separator.\n" "Usage: /addrule <file> | <rule text>",
            )


async def removerule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_authorized(update):
        hasTwoArgs = len(context.args) >= 2
        if hasTwoArgs:
            name = context.args[0]
            number_text = context.args[1]
            isNumber = number_text.isdigit()
            if isNumber:
                rules_repo.ensure_repo()
                ok, msg = rules_repo.remove_rule(name, int(number_text))
                if ok:
                    pushed_ok, push_msg = rules_repo.commit_and_push(
                        f"rules: remove #{number_text} from {name}"
                    )
                    await reply(update, f"✅ {msg}\n{push_msg}")
                else:
                    await reply(update, f"⚠️ {msg}")
            else:
                await reply(update, "Rule number must be a number.")
        else:
            await reply(update, "Usage: /removerule <file> <number>")


async def _require_active_project(update: Update) -> str | None:
    """Return the active todo project, or reply asking the user to set one."""
    project = todos_repo.active_project()
    has_active = project is not None
    if has_active:
        return project
    await reply(
        update,
        "No active todo project. Set one with /todo_use <project>, "
        "then /todo_add works against it.",
    )
    return None


async def todo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_authorized(update):
        project = todos_repo.active_project()
        has_active = project is not None
        if has_active:
            await reply(update, f"📌 Active todo project: {project}")
        else:
            await reply(
                update,
                "No active todo project yet. Set one with /todo_use <project>.",
            )


async def todo_use(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_authorized(update):
        hasArg = bool(context.args)
        if hasArg:
            project = context.args[0]
            todos_repo.set_active_project(project)
            await reply(
                update,
                f"📌 Active todo project is now: {project}\n"
                "This is separate from the coding agent's project.",
            )
        else:
            await reply(update, "Usage: /todo_use <project>")


async def todo_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_authorized(update):
        todos_repo.ensure_repo()
        names = todos_repo.list_projects()
        active = todos_repo.active_project()
        has_projects = len(names) > 0
        if has_projects:
            lines = ["🗂 Projects with todo lists:"]
            for name in names:
                marker = " (active)" if name == active else ""
                lines.append(f"- {name}{marker}")
            await reply(update, "\n".join(lines))
        else:
            await reply(
                update,
                "No todo lists yet. /todo_use <project> then /todo_add <text>.",
            )


async def todo_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_authorized(update):
        project = await _require_active_project(update)
        has_project = project is not None
        if has_project:
            todos_repo.ensure_repo()
            ok, body = todos_repo.numbered_todos(project)
            await reply(update, f"📋 {project} todos:\n{body}")


async def todo_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_authorized(update):
        project = await _require_active_project(update)
        has_project = project is not None
        if has_project:
            text = " ".join(context.args).strip()
            hasText = bool(text)
            if hasText:
                todos_repo.ensure_repo()
                ok, msg = todos_repo.add_todo(project, text)
                if ok:
                    _, push_msg = todos_repo.commit_and_push(f"todos: add to {project}")
                    await reply(update, f"✅ {msg}\n{push_msg}")
                else:
                    await reply(update, f"⚠️ {msg}")
            else:
                await reply(update, "Usage: /todo_add <text>")


async def todo_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_authorized(update):
        project = await _require_active_project(update)
        has_project = project is not None
        if has_project:
            hasArg = bool(context.args)
            isNumber = hasArg and context.args[0].isdigit()
            if isNumber:
                todos_repo.ensure_repo()
                ok, msg = todos_repo.complete_todo(project, int(context.args[0]))
                if ok:
                    _, push_msg = todos_repo.commit_and_push(
                        f"todos: complete in {project}"
                    )
                    await reply(update, f"✅ {msg}\n{push_msg}")
                else:
                    await reply(update, f"⚠️ {msg}")
            else:
                await reply(update, "Usage: /todo_done <number>  (see /todo_list)")


async def register_commands(app: Application) -> None:
    """Register commands so Telegram shows suggestions after typing `/`."""
    await app.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Registered %d Telegram command hints", len(BOT_COMMANDS))


def build_application() -> Application:
    app = (
        Application.builder()
        .token(config.PM_TELEGRAM_BOT_TOKEN)
        .post_init(register_commands)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(CommandHandler("core", core))
    app.add_handler(CommandHandler("sync", sync))
    app.add_handler(CommandHandler("files", files))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("addrule", addrule))
    app.add_handler(CommandHandler("removerule", removerule))
    app.add_handler(CommandHandler("todo", todo))
    app.add_handler(CommandHandler("todo_use", todo_use))
    app.add_handler(CommandHandler("todo_list", todo_list))
    app.add_handler(CommandHandler("todo_add", todo_add))
    app.add_handler(CommandHandler("todo_done", todo_done))
    app.add_handler(CommandHandler("todo_projects", todo_projects))
    return app
