"""Define the shared command catalog and Telegram hints."""

from ai_agent_common import Command, build_command_list, to_bot_commands

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
