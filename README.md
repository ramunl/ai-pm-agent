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
| /files | List all rule files in the repo |
| /rules \<file\> | Show numbered rules in a file |
| /addrule \<file\> \| \<rule text\> | Add a rule (creates file if new) |
| /removerule \<file\> \<number\> | Remove rule by its number |
| /sync | Pull the latest rules from GitHub |

Files are referenced by stem name: `kotlin` → `global/kotlin.md`,
`architecture` → `projects/channel-cast/architecture.md`. New files created
via /addrule are placed under `global/`.

### Examples

```
/addrule kotlin | Prefer sealed classes for UI state
/rules kotlin
/removerule kotlin 4
```

## How it connects to the coding agent

```
ai-rules (markdown)
   ↑ writes              ↓ reads
ai-pm-agent          ai-coding-agent
(this repo)          (injects rules into Claude prompts)
```

The PM agent is the only writer. The coding agent is a reader. They never
share logic — only the rules repo.

## Setup

```bash
# 1. Create a THIRD Telegram bot via @BotFather (e.g. @channelcast_pm_bot)

# 2. Clone and install
sudo git clone git@github.com:ramunl/ai-pm-agent.git /opt/ai-pm-agent
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
