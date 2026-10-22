"""Check threaded repository work and cancellation-safe transaction ownership."""

import asyncio
import threading
from unittest.mock import Mock

import pytest

from ai_pm_agent.bot.repository_actions import (
    publish_mutation,
    require_repository,
    run_repository,
)


@pytest.mark.parametrize("stage", ["sync", "edit", "publish"])
def test_blocked_repository_work_allows_loop_progress(stage, chat):
    async def scenario():
        started = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()

        def blocked():
            loop.call_soon_threadsafe(started.set)
            assert release.wait(3)
            return True, "finished"

        success = lambda: (True, "finished")
        if stage == "sync":
            operation = require_repository(chat, blocked)
        else:
            operation = publish_mutation(
                chat,
                blocked if stage == "edit" else success,
                blocked if stage == "publish" else success,
            )
        task = asyncio.create_task(operation)
        try:
            await asyncio.wait_for(started.wait(), 1)
            await asyncio.sleep(0)
            assert not task.done()
        finally:
            release.set()
            await task

    asyncio.run(scenario())


@pytest.mark.parametrize("fails", [False, True])
def test_repeated_cancellation_waits_for_worker(fails):
    async def scenario():
        started = asyncio.Event()
        release = threading.Event()
        finished = threading.Event()
        loop = asyncio.get_running_loop()

        def blocked():
            loop.call_soon_threadsafe(started.set)
            assert release.wait(3)
            finished.set()
            if fails:
                raise ValueError("worker failed")

        task = asyncio.create_task(run_repository(blocked))
        try:
            await asyncio.wait_for(started.wait(), 1)
            for _ in range(2):
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert finished.is_set()

    asyncio.run(scenario())


def test_failure_replies_and_publication_gate(chat):
    publish = Mock()
    assert not asyncio.run(require_repository(chat, lambda: (False, "offline")))
    chat.message.reply_text.assert_awaited_with("⚠️ Sync problem\noffline")
    asyncio.run(publish_mutation(chat, lambda: (False, "invalid"), publish))
    chat.message.reply_text.assert_awaited_with("⚠️ invalid")
    publish.assert_not_called()
