# ai-pm-agent

The PM bot of the owner's AI agent ecosystem (Telegram, one owner). It is the
only writer of two markdown repos: coding rules in `ai-rules` (read by the
coding agent's planner) and per-project TODO lists in `ai-todos`
(`projects/<project>/todo.md`). It publishes a secret-free snapshot for the
`ai-dashboard` PM window and answers the dashboard through a local JSON bridge
(`task_cli.py`: bounded stdin request, fixed operations, no paths or commands
from the caller). Runs as `ai-pm-agent.service` on a 1 GB VPS.

## Run and validate

- Run the bot: `python -m ai_pm_agent`.
- Install development dependencies: `python -m pip install -r requirements-dev.txt`.
- Format before committing: `ruff format ai_pm_agent tests`.
- Validate: `ruff check ai_pm_agent tests`, `ruff format --check ai_pm_agent tests`,
  and `python -m pytest -q`. Annotation and docstring checks are part of Ruff.
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

## Traps

- TODO items keep machine metadata in a trailing `<!-- pm-task:{...} -->`
  comment; edit through `task_model` / `task_service`, never by hand-made
  regexes, and keep old plain checkbox lines readable.
- Writes check the list revision (`TaskConflictError`) so a stale dashboard
  view can't overwrite newer edits.
- `ai_agent_common/` is a shared submodule; change it in its own repo.
