"""Configuration loaded from environment variables."""

import os

PM_TELEGRAM_BOT_TOKEN = os.environ["PM_TELEGRAM_BOT_TOKEN"]
AUTHORIZED_CHAT_ID = int(os.environ["YOUR_CHAT_ID"])

# Where the ai-rules repo is cloned on the server.
RULES_REPO_PATH = os.environ.get("RULES_REPO_PATH", "/opt/ai-rules")

# SSH remote for the rules repo (public repo, but push needs auth).
RULES_REPO_URL = os.environ.get(
    "RULES_REPO_URL", "git@github.com:ramunl/ai-rules.git"
)

# Git identity used for commits made by the agent.
GIT_AUTHOR_NAME = os.environ.get("PM_GIT_NAME", "ai-pm-agent")
GIT_AUTHOR_EMAIL = os.environ.get("PM_GIT_EMAIL", "ai-pm-agent@localhost")

# Max characters per Telegram message (hard limit is 4096).
TELEGRAM_MESSAGE_LIMIT = 4000
