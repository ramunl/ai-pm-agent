"""Telegram bot for managing coding rules in the ai-rules repo."""

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from . import config, rules_repo

logger = logging.getLogger(__name__)


def is_authorized(update: Update) -> bool:
    isAuthorized = (
        update.message is not None
        and update.message.chat_id == config.AUTHORIZED_CHAT_ID
    )
    if not isAuthorized:
        logger.warning(
            "Ignored message from unauthorized chat: %s",
            update.message.chat_id if update.message else "unknown",
        )
    return isAuthorized


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
            "📐 PM Agent — rules management\n\n"
            "/files - list all rule files\n"
            "/rules <file> - show rules in a file\n"
            "/addrule <file> | <rule text> - add a rule\n"
            "/removerule <file> <number> - remove a rule\n"
            "/sync - pull latest rules from GitHub\n\n"
            "Example:\n"
            "/addrule kotlin | Prefer sealed classes for UI state",
        )


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
                "Missing separator.\n"
                "Usage: /addrule <file> | <rule text>",
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


def build_application() -> Application:
    app = Application.builder().token(config.PM_TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sync", sync))
    app.add_handler(CommandHandler("files", files))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("addrule", addrule))
    app.add_handler(CommandHandler("removerule", removerule))
    return app
