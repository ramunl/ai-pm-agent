# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Telegram bot that is the **sole writer** of the [ai-rules](https://github.com/ramunl/ai-rules) repo — a separate git repo of markdown coding rules. The bot lets an authorized user add/list/remove rules from Telegram; every mutation is committed and pushed to GitHub automatically. It is part of a multi-agent ecosystem (coding agent reads the rules, ops agent watches the server); those other agents are separate repos and share nothing with this one except the ai-rules working copy.

Code review against rules is intentionally **not** implemented yet — see README.

## Running & ops

```bash
python -m ai_pm_agent          # run the bot (long-polling)
pip install -r requirements.txt
```

Deployed as a systemd service (`ai-pm-agent.service`) running `/opt/ai_pm_venv/bin/python -m ai_pm_agent`, with secrets in `/etc/ai-pm-agent.env`. There is **no test suite, linter config, or git repo** here — `python -m ai_pm_agent` is the only way to exercise the code, and it requires the env vars below to be set or it raises `KeyError` at import time.

## Required environment

Set before running (see `ai_pm_agent/config.py`): `PM_TELEGRAM_BOT_TOKEN` and `YOUR_CHAT_ID` are mandatory. Optional: `RULES_REPO_PATH` (default `/opt/ai-rules`), `RULES_REPO_URL`, `PM_GIT_NAME`, `PM_GIT_EMAIL`.

## Architecture (3 layers, strict one-way dependency)

`telegram_bot.py` → `rules_repo.py` → `shell.py`. Config is a leaf imported by all.

- **`telegram_bot.py`** — command handlers + the one authorization gate. Every handler starts with `if is_authorized(update)` (chat_id must equal `AUTHORIZED_CHAT_ID`); unauthorized messages are silently dropped and logged. Most handlers call `rules_repo.ensure_repo()` first to sync, then mutate, then `commit_and_push()`.
- **`rules_repo.py`** — all rules logic and the only git-writing code. A **rule file** is any `*.md` in the repo (except top-level READMEs); a **rule** is a markdown bullet (`- ...`) line within it. Files are addressed by stem name (`kotlin` → `global/kotlin.md`) via `_resolve_file`, and rules by 1-based index over `_bullet_lines`. New files from `/addrule` are created under `global/`.
- **`shell.py`** — the **only** place subprocesses run. `run()` takes an argument **list** (never `shell=True`) and returns `(ok, output)`. All git operations flow through it.

The `(ok: bool, output: str)` tuple is the convention threaded through `rules_repo` and `shell` back up to the bot.

## Conventions to follow when editing

- Never introduce `shell=True` or string-built commands — route every external process through `shell.run([...])` with a fixed argument list. This is the core security property (no free-form shell exec).
- Keep the authorization check at the top of every new command handler.
- The codebase favors named boolean locals (`is_new_file`, `hasSeparator`, `nothing_to_commit`) describing a condition before branching on it — match that style rather than inlining complex conditionals.
- Rules-repo git is **main-only**: pulls are `--ff-only origin main`, pushes go to `origin main`.
