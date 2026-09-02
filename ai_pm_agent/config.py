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

# Where the ai-todos repo is cloned on the server.
TODOS_REPO_PATH = os.environ.get("TODOS_REPO_PATH", "/opt/ai-todos")

# SSH remote for the todos repo.
TODOS_REPO_URL = os.environ.get(
    "TODOS_REPO_URL", "git@github.com:ramunl/ai-todos.git"
)

# File holding the PM agent's own active todo project. Deliberately separate
# from the coding agent's active project: the two are not coupled.
TODOS_STATE_FILE = os.environ.get(
    "TODOS_STATE_FILE", "/opt/ai-todos-active.txt"
)

# Git identity used for commits made by the agent.
GIT_AUTHOR_NAME = os.environ.get("PM_GIT_NAME", "ai-pm-agent")
GIT_AUTHOR_EMAIL = os.environ.get("PM_GIT_EMAIL", "ai-pm-agent@localhost")

# Max characters per Telegram message (hard limit is 4096).
TELEGRAM_MESSAGE_LIMIT = 4000
