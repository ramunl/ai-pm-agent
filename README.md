# ai-pm-agent

Project-manager agent for the coding-agent ecosystem. Its first job is
**rules management**: it owns the contents of the [ai-rules](https://github.com/ramunl/ai-rules)
repo and lets you add, list, and remove coding rules from Telegram. Every
change is committed and pushed to GitHub automatically.

Code review against the rules is intentionally **not** in this version — it
only becomes useful once the coding agent reads the rules when generating
code. Build that wiring first; review comes later.

## Agent ecosystem

- [ai-coding-agent](https://github.com/ramunl/ai-coding-agent) — implements features and bugfixes
- **ai-pm-agent** (this repo) — manages rules (review later)
- [ai-rules](https://github.com/ramunl/ai-rules) — coding rules storage (not an agent)
- [ai-ops-agent](https://github.com/ramunl/ai-ops-agent) — server health, logs, updates

## Commands

| Command | Description |
|---|---|
| /help | Show the shared command catalog |
| /version | Show the agent, branch, commit, and shared-core version |
| /core | Show the pinned shared-core release |
| /files | List all rule files in the repo |
| /rules \<file\> | Show numbered rules in a file |
| /addrule \<file\> \| \<rule text\> | Add a rule (creates file if new) |
| /removerule \<file\> \<number\> | Remove rule by its number |
| /sync | Pull the latest rules from GitHub |

Use exact relative paths from `/files`, such as `global/kotlin.md` or
`projects/channel-cast/architecture.md`, with `/rules`, `/addrule` and
`/removerule`. Exact paths take precedence. Case-insensitive stems, filenames
and paths without `.md` also work when they match exactly one file. Ambiguous
shorthand returns sorted matching relative paths without editing or publishing.

`/addrule` creates missing files only from simple names, under `global/<name>.md`.
Names and relative-path components must be 1–80 ASCII letters, digits,
underscores, dots or hyphens, starting with a letter or digit. Relative selectors
must identify existing files; missing paths never create files. Absolute paths,
traversal and symlinks escaping the repository are rejected.

### Examples

```
/addrule kotlin | Prefer sealed classes for UI state
/rules kotlin
/removerule global/kotlin.md 4
```

## How it connects to the coding agent

```
ai-rules (markdown)
   ↑ writes              ↓ reads
ai-pm-agent          ai-coding-agent
(this repo)          (injects rules into Claude prompts)
```

The PM agent is the only rules writer. The coding agent is a rules reader.
All agent bots share infrastructure through the `ai-agent-common` submodule.

## Setup

```bash
# 1. Create a THIRD Telegram bot via @BotFather (e.g. @channelcast_pm_bot)

# 2. Clone and install
sudo git clone --recurse-submodules git@github.com:ramunl/ai-pm-agent.git /opt/ai-pm-agent
python3 -m venv /opt/ai_pm_venv
/opt/ai_pm_venv/bin/pip install -r /opt/ai-pm-agent/requirements.txt

# 3. Configure environment
sudo tee /etc/ai-pm-agent.env > /dev/null <<ENVEOF
PM_TELEGRAM_BOT_TOKEN=your-new-pm-bot-token
YOUR_CHAT_ID=your-chat-id
RULES_REPO_PATH=/opt/ai-rules
RULES_REPO_URL=git@github.com:ramunl/ai-rules.git
ENVEOF
sudo chmod 600 /etc/ai-pm-agent.env

# 4. Install as systemd service
sudo cp /opt/ai-pm-agent/ai-pm-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ai-pm-agent

# 5. Test in Telegram: send /start to your PM bot
```

## Push access to ai-rules

ai-rules is public, but pushing still needs auth. Two options:

1. **Reuse the server's existing SSH key** (simplest, already set up for the
   coding agent). The agent will push as your GitHub user.
2. **Deploy key (recommended for least privilege):** generate a key dedicated
   to this service with write access scoped to ai-rules only, and point
   `GIT_SSH_COMMAND` at it in the service environment. This keeps the PM
   agent from being able to push to your other repos.

## Security notes

- Token in `/etc/ai-pm-agent.env` (chmod 600), never in code
- Only the authorized chat ID can issue commands; others are ignored + logged
- No free-form shell execution — git operations use fixed argument lists
- The agent only ever touches the ai-rules working copy

## TODO lists (per project)

The PM agent also manages per-project TODO lists in a separate `ai-todos`
repo, stored as `projects/<project>/todo.md` with markdown checkboxes.

| Command | Description |
|---|---|
| /todo | Show the active todo project |
| /todo_use \<project\> | Switch the active todo project |
| /todo_list | Show open items for the active project |
| /todo_add \<text\> | Add an item to the active project |
| /todo_done \<number\> | Mark open item N done (by /todo_list number) |
| /todo_projects | List projects that have todo lists |

### Independent active-project state

The todo list has its **own** active project, stored on the server in
`TODOS_STATE_FILE`, deliberately separate from the coding agent's active
project. Switching the coding agent's project with `/repo_use` does **not**
change which todo list is active, and vice versa. This avoids coupling two
processes through shared state. Every todo reply names the active project so
the two can never drift silently.

Because completing an item marks it `- [x]` rather than deleting it,
`/todo_done` numbers refer to **open** items only; the numbering shifts after
each completion, so re-run `/todo_list` before the next `/todo_done`.

### Setup

```bash
# Create the ai-todos repo on GitHub, then on the server it clones on first use.
# Env (optional; sane defaults shown):
TODOS_REPO_PATH=/opt/ai-todos
TODOS_REPO_URL=git@github.com:ramunl/ai-todos.git
TODOS_STATE_FILE=/opt/ai-todos-active.txt
```

## Dashboard snapshot

The PM agent publishes a secret-free read model for the separate
**ai-dashboard** service, which shows it as the PM window (`/pm`):

- file: `PM_SNAPSHOT_FILE` (default `/var/lib/ai-pm-agent/snapshot.json`), mode 0600
- written on change and at least every 30 s (heartbeat), atomically
- content (`"format": 1`): active todo project, its open items (first 50) and
  done count, every project's open/done counts, rule files with rule counts,
  agent and core version

Todo and rule parsing stays in `todos_repo` / `rules_repo`
(`todo_summary()`, `rule_counts()`), so the dashboard never parses these files
itself. Publishing starts with the bot and never blocks or crashes it.

## Development

Follow the Python rules in `ai-rules/global/python.md`. Telegram adapters live in
`ai_pm_agent/bot`; rules and TODO markdown operations share the Git service in
`ai_pm_agent/git_repo.py`. See [architecture and edit flow](docs/architecture.md).

```bash
python -m pip install -r requirements-dev.txt
ruff check ai_pm_agent tests
ruff format --check ai_pm_agent tests
python -m pytest -q
```

Run `ruff format ai_pm_agent tests` before committing. CI uses Python 3.12 and
runs these checks on pull requests and pushes to `main`.

Commands now stop before editing if repository synchronization fails. A failed
Git configuration, staging, commit, or push is reported as a failure; a failed
push no longer receives a success checkmark. Successful command syntax and
markdown numbering are unchanged.

## Todos workspace and dashboard editing

The dashboard Todos workspace supports project selection/creation, adding,
editing, confirmed deletion, priorities (`high`, `normal`, `low`) and statuses
(`open`, `in_progress`, `blocked`, `done`). “Open” lists include all unfinished
items; completed items can be reopened. The PM project remains independent of
coding-agent repository selection.

Additional Telegram commands use the same structured task operations:

| Command | Action |
|---|---|
| `/todo_edit <open number> \| <text>` | Edit an item |
| `/todo_remove <open number>` | Delete an item |
| `/todo_priority <open number> <high\|normal\|low>` | Set priority |
| `/todo_status <open number> <open\|in_progress\|blocked\|done>` | Set status |
| `/todo_completed` | List completed text and stable IDs |
| `/todo_reopen <id>` | Reopen a completed item |

Task text remains one Markdown checkbox line. The dashboard folds entered line
breaks into spaces. Machine metadata lives in trailing `<!-- pm-task:{...} -->`
comments: ID, status, type, priority and, for items added from now on, a UTC `created`
date. Missing types default to Feature on plain and older structured tasks.
Existing plain checkboxes default to Normal priority and have no creation
date. Their IDs become persistent on the first edit to that project; all
other paragraphs and completed history are preserved. IDs are distinct even
when two tasks have identical text. Bot lists hide the metadata and show Feature,
Bug or Notice alongside priority/status labels. Existing items therefore display
Feature until their type is changed.

The local JSON bridge is owned by this repository. The dashboard sends a fixed
operation as JSON on stdin; it never edits TODO Markdown directly. All Telegram
TODO operations and bridge transactions share a filesystem lock. Mutation
requests accept `type` on add/update: exactly `feature`, `bug` or `notice`.
Untyped adds (including Telegram adds) default to `feature`; updates that omit
`type` preserve it. Invalid explicit types, including `null`, are rejected
without editing TODO files. Workspace items return `type` for all tasks. Mutation
requests include project, task ID and a content revision, so a stale screen
cannot edit a different task. Add requests reuse their ID when retrying;
retries with the same ID/text retain the stored type and identity.

Snapshot `todos.items[]` also includes `type`, alongside `index`, `text`,
`created` and `priority`. Format `1`, legacy `todos.open` strings, file order
and open-item numbering are unchanged. Dashboard type display and editing via
a selector are deferred to part 2 in ai-dashboard. See the
[metadata and bridge contracts](docs/architecture.md#todomd-metadata) for details.

A failed pull stops edits. A failed push reports “saved locally” and returns the
updated workspace; **Sync todos** pulls and retries publishing existing commits.
Do not resubmit a task under a new ID following an uncertain response.

Install the bridge once after deploying this repository:

```bash
sudo install -m 755 /opt/ai-pm-agent/deploy/ai-pm-todos /usr/local/sbin/ai-pm-todos
```

The wrapper uses `/etc/ai-pm-agent.env` and `/opt/ai_pm_venv`, matching the PM
service. Keep the environment file owner-only. Task IDs, statuses, and the
transport-neutral `task_service.execute()` are foundations for a future worker;
this release does not claim or execute tasks automatically.

## Deployment webhook

Pushes to `main` or a manual run of `Deploy AI PM Agent` call the HTTPS hook.
Set GitHub Actions secrets `DEPLOY_WEBHOOK_URL` to
`https://<deploy-host>/hooks/ai-pm-agent-update` and `DEPLOY_WEBHOOK_TOKEN` to
the matching server token. The workflow sends the token as a bearer header;
credentials in URLs, HTTP, redirects, and HTTP errors fail the job.
