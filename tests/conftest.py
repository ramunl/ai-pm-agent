"""Configure test credentials and Telegram messages for PM command tests."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("PM_TELEGRAM_BOT_TOKEN", "123456:test-token")
os.environ.setdefault("YOUR_CHAT_ID", "123456")


@pytest.fixture
def chat():
    from ai_pm_agent import config

    return SimpleNamespace(
        message=SimpleNamespace(
            chat_id=config.AUTHORIZED_CHAT_ID,
            reply_text=AsyncMock(),
        )
    )
