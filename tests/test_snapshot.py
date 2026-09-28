"""The PM agent's published read model: the dashboard's only input for /pm."""

import asyncio
import importlib
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("PM_TELEGRAM_BOT_TOKEN", "123456:test-token")
os.environ.setdefault("YOUR_CHAT_ID", "123456")

_ENV_KEYS = (
    "TODOS_REPO_PATH",
    "RULES_REPO_PATH",
    "TODOS_STATE_FILE",
    "PM_SNAPSHOT_FILE",
)
VERSIONS = {"version": "ai-pm-agent v1", "core": "core: v1.1"}


class SnapshotTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {key: os.environ.get(key) for key in _ENV_KEYS}
        self.tmp = Path(tempfile.mkdtemp())
        self.todos_dir = self.tmp / "ai-todos"
        self.rules_dir = self.tmp / "ai-rules"
        (self.todos_dir / "projects").mkdir(parents=True)
        (self.rules_dir / "global").mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=self.todos_dir, check=True)
        os.environ["TODOS_REPO_PATH"] = str(self.todos_dir)
        os.environ["RULES_REPO_PATH"] = str(self.rules_dir)
        os.environ["TODOS_STATE_FILE"] = str(self.tmp / "active.txt")
        os.environ["PM_SNAPSHOT_FILE"] = str(self.tmp / "snapshot.json")

        from ai_pm_agent import config, rules_repo, snapshot, todos_repo

        for module in (config, todos_repo, rules_repo, snapshot):
            importlib.reload(module)
        self.todos, self.rules, self.snapshot = todos_repo, rules_repo, snapshot

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _todo_file(self, project: str, text: str) -> None:
        path = self.todos_dir / "projects" / project / "todo.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


class SummaryTests(SnapshotTestCase):
    def test_todo_summary(self) -> None:
        self._todo_file(
            "channel-cast",
            "# t\n\n- [ ] fix proxy\n- [x] add genre filter\n- [ ] release apk\n",
        )
        self.assertEqual(
            self.todos.todo_summary("channel-cast"),
            {"open": ["fix proxy", "release apk"], "done": 1},
        )

    def test_todo_summary_without_list(self) -> None:
        self.assertEqual(
            self.todos.todo_summary("nothing-here"), {"open": [], "done": 0}
        )

    def test_rule_counts_skip_readme(self) -> None:
        (self.rules_dir / "README.md").write_text("- not a rule\n")
        (self.rules_dir / "global" / "kotlin.md").write_text(
            "# Kotlin\n- a\n- b\n- c\n"
        )
        self.assertEqual(
            self.rules.rule_counts(), [{"file": "global/kotlin.md", "count": 3}]
        )


class ContentTests(SnapshotTestCase):
    def test_active_project_projects_and_rules(self) -> None:
        self._todo_file("channel-cast", "- [ ] fix proxy\n- [x] done one\n")
        self._todo_file("other-app", "- [ ] set up CI\n")
        (self.rules_dir / "global" / "kotlin.md").write_text("- a\n")
        self.todos.set_active_project("channel-cast")

        content = self.snapshot.build_content(VERSIONS)

        self.assertEqual(content["format"], 1)
        self.assertEqual(content["active_project"], "channel-cast")
        self.assertEqual(
            content["todos"],
            {
                "project": "channel-cast",
                "open": ["fix proxy"],
                "open_count": 1,
                "done": 1,
            },
        )
        self.assertEqual(
            content["projects"],
            [
                {"name": "channel-cast", "open": 1, "done": 1},
                {"name": "other-app", "open": 1, "done": 0},
            ],
        )
        self.assertEqual(content["rules"], [{"file": "global/kotlin.md", "count": 1}])
        self.assertEqual(content["core"], "core: v1.1")

    def test_no_active_project(self) -> None:
        content = self.snapshot.build_content(VERSIONS)
        self.assertIsNone(content["active_project"])
        self.assertIsNone(content["todos"])

    def test_long_lists_are_capped_but_counted(self) -> None:
        items = "".join(f"- [ ] item {i}\n" for i in range(80))
        self._todo_file("big", items)
        self.todos.set_active_project("big")
        todos = self.snapshot.build_content(VERSIONS)["todos"]
        self.assertEqual(len(todos["open"]), self.snapshot.MAX_OPEN_ITEMS)
        self.assertEqual(todos["open_count"], 80)


class PublisherTests(SnapshotTestCase):
    def test_change_heartbeat_and_permissions(self) -> None:
        path = self.tmp / "snapshot.json"
        publisher = self.snapshot.SnapshotPublisher(path, heartbeat=30)
        content = self.snapshot.build_content(VERSIONS)
        self.assertTrue(publisher.publish(content, now=1000.0))
        self.assertFalse(publisher.publish(dict(content), now=1010.0))
        self.assertTrue(publisher.publish(dict(content), now=1031.0))
        self.assertTrue(
            publisher.publish({**content, "active_project": "x"}, now=1032.0)
        )
        saved = json.loads(path.read_text())
        self.assertEqual((saved["updated_at"], saved["active_project"]), (1032.0, "x"))
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_loop_survives_a_failing_tick(self) -> None:
        path = self.tmp / "snapshot.json"
        real = self.snapshot.build_content
        calls = {"n": 0}

        def flaky(version_info: dict) -> dict:
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("todos repo mid-pull")
            return real(version_info)

        async def run() -> None:
            with (
                patch.object(self.snapshot, "versions", return_value=VERSIONS),
                patch.object(self.snapshot, "build_content", side_effect=flaky),
            ):
                task = asyncio.create_task(
                    self.snapshot.publish_forever(path, interval=0.01)
                )
                for _ in range(200):
                    if path.exists():
                        break
                    await asyncio.sleep(0.01)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

        asyncio.run(run())
        self.assertGreaterEqual(calls["n"], 2)
        self.assertEqual(json.loads(path.read_text())["format"], 1)


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_registers_hints_and_starts_publisher_shutdown_stops_it(
        self,
    ) -> None:
        from ai_pm_agent import snapshot, telegram_bot

        started = asyncio.Event()

        async def fake_publish(path: Path) -> None:
            started.set()
            await asyncio.Event().wait()

        app = AsyncMock()
        with patch.object(snapshot, "publish_forever", fake_publish):
            await telegram_bot.on_startup(app)
            await asyncio.wait_for(started.wait(), timeout=1)
            self.assertIsNotNone(telegram_bot._publisher_task)
            await telegram_bot.on_shutdown(app)
        app.bot.set_my_commands.assert_awaited_once()
        self.assertIsNone(telegram_bot._publisher_task)


if __name__ == "__main__":
    unittest.main()
