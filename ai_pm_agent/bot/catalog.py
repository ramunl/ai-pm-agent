"""Define command names and autocomplete descriptions."""

from __future__ import annotations

from telegram import BotCommand

BOT_COMMANDS = (
    BotCommand("start", "Show available commands"),
    BotCommand("files", "List all rule files"),
    BotCommand("rules", "Show rules in a file"),
    BotCommand("addrule", "Add a rule"),
    BotCommand("removerule", "Remove a rule"),
    BotCommand("sync", "Pull the latest rules from GitHub"),
    BotCommand("todo", "Show the active todo project"),
    BotCommand("todo_use", "Switch the active todo project"),
    BotCommand("todo_list", "Show todos for the active project"),
    BotCommand("todo_add", "Add a todo to the active project"),
    BotCommand("todo_done", "Mark a todo done by number"),
    BotCommand("todo_projects", "List projects that have todo lists"),
)
