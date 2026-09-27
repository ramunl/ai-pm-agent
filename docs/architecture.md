# PM agent architecture

`ai_pm_agent.telegram_bot` constructs the application and registers autocomplete
commands. `python -m ai_pm_agent` remains the entry point. Existing command names,
rule numbering, TODO numbering, and the independent active-project state remain.

## Responsibilities

| Module | Owns |
| --- | --- |
| `bot/catalog.py` | Autocomplete command metadata |
| `bot/transport.py` | Owner authorization and bounded plain-text replies |
| `bot/help.py` | Shared command reference, runtime version, and core status |
| `bot/rules.py` | Rule command validation and orchestration |
| `bot/todos.py` | TODO project selection and command orchestration |
| `bot/repository_actions.py` | Synchronization gates and publication-result replies |
| `rules_repo.py` | Rule-file lookup and markdown bullet edits |
| `todos_repo.py` | TODO files, open-item numbering, and PM-owned active state |
| `git_repo.py` | Shared clone, fast-forward, commit, and push operations |
| `shell.py` | Subprocess execution with argument lists |
| `config.py` | Repository paths, remotes, identity, and Telegram settings |
| `snapshot.py` | Dashboard read model, atomic writes, and heartbeat publishing |

Dependencies flow from command adapters to repositories, the shared Git service,
and shell execution. Neither repository imports command handlers. Rules and TODO
repositories keep their existing public functions; those functions build an
immutable `RepositoryConfig` from current settings and delegate Git operations.

Shared-core authorization and command catalogs remain in use. Application startup
registers commands and starts the snapshot publisher; shutdown cancels and awaits
the publisher. The dashboard snapshot format and file permissions are unchanged.

## Edit and publication flow

Handlers reject unauthorized messages first and validate arguments before doing
repository work. A repository is synchronized before reading or editing it.
Synchronization failure stops the operation before any markdown mutation.

After a successful local edit, the Git service configures the commit identity,
stages changes, commits, and pushes `origin main`. Each Git failure stops the
sequence. A clean tree reports that there are no changes to push. Publication
failures use a warning reply instead of a success checkmark; local edits remain
available when Git publication fails.

The active TODO project continues to live in `TODOS_STATE_FILE`, separately from
the coding agent's project selection. Done items remain `- [x]` markdown lines;
user-facing numbers continue to refer only to open items.

## Validation

CI runs Ruff formatting, import/error linting, public docstring and type-hint
checks, and pytest on Python 3.12. Tests cover command registration, unauthorized
messages, argument validation, sync and publication failures, markdown edits,
active-project state, open-item numbering, and reply truncation.

Git publication is tested with mocked command results. Markdown tests use
temporary repositories and do not push to the live rules or TODO remotes.
