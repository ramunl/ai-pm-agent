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
the publisher. The dashboard snapshot format number and file permissions are
unchanged; todo items gained additive sort fields (see below).

## Edit and publication flow

Handlers reject unauthorized messages first and validate arguments before doing
repository work. A repository is synchronized before reading or editing it.
Synchronization failure stops the operation before any markdown mutation.

Repository synchronization, mutation callables, and Git publication run via
`asyncio.to_thread` in `bot/repository_actions.py`. Structured task edits also
run `task_service.execute` (including its synchronization and publication) in a
worker, as do their initial synchronization and workspace reads. Git timeouts
still delay the requesting command, but leave the event loop available for
Telegram polling and snapshot heartbeats.

Telegram TODO and rules handlers hold the shared `task_lock.serialized` file
lock across awaited repository operations, from synchronization through editing
and publication. Rules use the same lock to prevent concurrent rules commands
from interleaving. The event-loop handler owns and closes the lock handle; the
worker does not acquire it again. `task_service.execute` relies on the caller's
transaction lock and has no nested lock acquisition or thread-local lock state.
The worker helper shields its task and, even after repeated cancellation, waits
for worker completion before propagating cancellation. This prevents the handler
from releasing protection while a cancelled command's worker still changes
files. Cancellation stops subsequent command steps; completed local edits may
remain unpublished if cancellation occurs before publication starts.


`/addrule` accepts names matching `[A-Za-z0-9][A-Za-z0-9_.-]{0,79}`:
1–80 ASCII characters, starting with a letter or digit, followed by letters,
digits, underscores, dots or hyphens. The shared validator runs after owner
authorization and required-argument checks, before synchronization, and again
inside `add_rule` for direct callers. Absolute paths, separators, traversal and
relative-path selectors such as `global/python.md` are rejected. Existing files
can be selected by stem or filename; duplicate stems in different directories
remain ambiguous and use the first sorted match. `/addrule` cannot disambiguate
them with a relative path.

Rule file targets (existing or new) and the repository root are resolved before
directory creation, content reads or writes. Targets must remain within the
resolved repository, including when file or directory symlinks are involved.
Containment failures return a failed result and prevent publication; rule counts
skip unsafe targets. New files still default to `global/`. These checks do not
prevent a concurrent local process from swapping symlinks between validation and
writing.

Telegram `/todo_done` and `/todo_list` reply with the repository's validation or
revision-conflict error text and stop without publication or a success reply.
Their `ValueError` handling covers only `complete_todo` and `numbered_todos`;
repository errors remain available to other callers. Completion keeps revision
protection, so a stale edit cannot overwrite newer TODO content. `/todo_add`
continues to report repository validation failures through its failed result.

After a successful local edit, the Git service configures the commit identity,
stages changes, commits, and pushes `origin main`. Each Git failure stops the
sequence, except that "nothing to commit" still proceeds to push. No-op edits in
both rules and TODO repositories retry publication of pending local commits.
The push outcome determines publication success, including network or
authentication failures on a clean tree. Publication failures use a warning reply
instead of a success checkmark; local edits remain available when Git publication
fails. The TODO bridge's `published` and `warning` fields reflect the retry result,
and Telegram confirms a push only when `published` is true.

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

## Interactive Todos workspace

`task_model.py` owns stable task metadata, Markdown compatibility, project path
validation, atomic writes and revision conflict checks. `task_service.py` exposes
transport-neutral workspace and mutation operations. `task_cli.py` is the local
JSON bridge used by ai-dashboard through the installed `deploy/ai-pm-todos`
wrapper. `task_lock.py` serializes CLI transactions and Telegram TODO handlers
across processes. Bot adapters retain open-item numbering for compatibility;
web requests use explicit project, stable ID and content revision.

Workspace project summaries use `todos_repo.todo_summary()` to count checkbox
markers without validating task metadata, including legacy lines and uppercase
`X` completion markers. Malformed metadata in another project therefore does not
block reads or mutation responses for a valid project. The selected project's
items still use strict `task_model.load()` validation; selecting a malformed
project returns a validation error until its metadata is repaired. Mutations
retain strict validation and revision conflict checks. Reading or editing an
explicit project does not change the independent PM active-project selection.

### todo.md metadata

Machine metadata lives in one trailing comment per item, edited only through
`task_model`:

```markdown
- [ ] Ship the release <!-- pm-task:{"id":"<32 hex>","status":"open","priority":"high","created":"2026-10-15"} -->
```

- `priority` is `high`, `normal` or `low`; plain checkbox lines read as `normal`.
- `created` is the UTC `YYYY-MM-DD` date when the item was added. Only `add`
  stamps it. Edits, status changes, deletions of other items and manual line
  reordering keep it. Items written earlier have no `created` key and parse as
  `None`. Dates are never backfilled, and rewrites leave the key out, so those
  lines stay byte-identical.
- Telegram replies, the snapshot `text`/`open` fields and the bridge `text`
  field never include the comment. The bridge returns `created` and `priority`
  as separate item fields.

### Snapshot todo fields

`todos.open` (a list of text strings) is kept for older dashboards. `todos.items`
lists the same open items, capped at `MAX_OPEN_ITEMS` like `open`. Each item has:

| Field | Value |
| --- | --- |
| `index` | 1-based position among open items in file order (the `/todo_done` number) |
| `text` | Item text without metadata |
| `created` | ISO date string, or `null` for older items (sort these last) |
| `priority` | `high`, `normal` or `low` (stored value, default `normal`) |

The field names are the contract with ai-dashboard browser-side sorting. The
snapshot `format` stays `1` because the change only adds fields.

The snapshot remains the read-only availability fallback. Live editing reads the
bridge for complete items, including done tasks. Rules editing remains in its
existing bot commands; a Rules UI is a later phase. Task claiming, execution and
completion evidence are future worker features.
