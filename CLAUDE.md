# Repository guidance

This project is the PM agent for the coding-agent ecosystem. It owns edits to
coding rules in `ai-rules` and per-project TODO lists in `ai-todos`.

## Run and validate

- Run the bot: `python -m ai_pm_agent`.
- Install development dependencies: `python -m pip install -r requirements-dev.txt`.
- Format before committing: `ruff format ai_pm_agent tests`.
- Validate: `ruff check ai_pm_agent tests`, the type-hint/docstring check documented
  in README, and `python -m pytest -q`.
- Tests use dummy credentials and temporary repositories; do not start the live
  bot to validate a code change.

## Configuration

`PM_TELEGRAM_BOT_TOKEN` and `YOUR_CHAT_ID` are required when importing app config.
Optional settings include repository paths/remotes, commit identity, and
`TODOS_STATE_FILE`. Production runs as `ai-pm-agent.service` with its configured
environment file.

## Architecture and conventions

Follow `ai-rules/global/python.md` and [the module map](docs/architecture.md).
Dependency flow is Telegram adapters → markdown repositories → shared Git service
→ shell execution. Configuration is a leaf dependency.

- Keep the owner authorization guard at the beginning of command handlers.
- Validate arguments and stop on failed synchronization before editing files.
- External commands go through `shell.run()` with argument lists, never
  `shell=True` or user-built command strings.
- Rules and TODO Git operations pull `--ff-only origin main` and push `origin main`.
- Check and report failures at every publication step.
- Preserve the independent PM active-project state and open-item TODO numbering.
- Update relevant markdown documentation with behavior or architecture changes.
