"""Handle coding-rule inspection and edits."""

from functools import partial

from telegram import Update
from telegram.ext import ContextTypes

from ai_pm_agent import rules_repo
from ai_pm_agent.bot.repository_actions import publish_mutation, require_repository
from ai_pm_agent.bot.transport import is_authorized, reply


async def sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pull the latest coding rules and report synchronization status."""
    if not is_authorized(update):
        return
    ok, output = rules_repo.ensure_repo()
    prefix = "✅ Synced" if ok else "⚠️ Sync problem"
    await reply(update, f"{prefix}\n{output}")


async def files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List available coding-rule files after synchronizing the repository."""
    if not is_authorized(update):
        return
    if not await require_repository(update, rules_repo.ensure_repo):
        return
    names = rules_repo.list_files()
    text = (
        "🗂 Rule files:\n" + "\n".join(names)
        if names
        else "No rule files yet. Add one with /addrule."
    )
    await reply(update, text)


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the numbered rules in a selected file."""
    if not is_authorized(update):
        return
    if not context.args:
        await reply(update, "Usage: /rules <file>  (see /files)")
        return
    if not await require_repository(update, rules_repo.ensure_repo):
        return
    name = context.args[0]
    ok, body = rules_repo.numbered_rules(name)
    header = f"📋 {name}:\n" if ok else ""
    await reply(update, header + body)


async def addrule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Validate, add, and publish a rule in the selected file."""
    if not is_authorized(update):
        return
    raw = " ".join(context.args)
    if "|" not in raw:
        await reply(update, "Missing separator.\nUsage: /addrule <file> | <rule text>")
        return
    file_part, _, rule_part = raw.partition("|")
    name, rule_text = file_part.strip(), rule_part.strip()
    if not name or not rule_text:
        await reply(
            update,
            "Both file and rule text are required.\nUsage: /addrule <file> | <rule text>",
        )
        return
    if not await require_repository(update, rules_repo.ensure_repo):
        return
    await publish_mutation(
        update,
        rules_repo.add_rule(name, rule_text),
        partial(rules_repo.commit_and_push, f"rules: add to {name}"),
    )


async def removerule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a numbered rule and publish the resulting file."""
    if not is_authorized(update):
        return
    if len(context.args) < 2:
        await reply(update, "Usage: /removerule <file> <number>")
        return
    name, number_text = context.args[:2]
    if not number_text.isdigit():
        await reply(update, "Rule number must be a number.")
        return
    if not await require_repository(update, rules_repo.ensure_repo):
        return
    await publish_mutation(
        update,
        rules_repo.remove_rule(name, int(number_text)),
        partial(
            rules_repo.commit_and_push, f"rules: remove #{number_text} from {name}"
        ),
    )
