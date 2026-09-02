"""Tests for per-project todo lists and PM-owned active project state."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("PM_TELEGRAM_BOT_TOKEN", "123456:test-token")
os.environ.setdefault("YOUR_CHAT_ID", "123456")


class TodosRepoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "ai-todos"
        (self.repo / "projects").mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)

        # Point config at this throwaway repo and a temp state file.
        os.environ["TODOS_REPO_PATH"] = str(self.repo)
        os.environ["TODOS_STATE_FILE"] = str(self.tmp / "active.txt")

        import importlib

        from ai_pm_agent import config as config_module
        importlib.reload(config_module)
        from ai_pm_agent import todos_repo as todos_module
        importlib.reload(todos_module)
        self.todos = todos_module

    # ---- active project state (PM-owned, independent) ----

    def test_active_project_unset_by_default(self) -> None:
        self.assertIsNone(self.todos.active_project())

    def test_set_and_read_active_project(self) -> None:
        self.todos.set_active_project("channel-cast")
        self.assertEqual(self.todos.active_project(), "channel-cast")

    def test_active_project_persists_across_reads(self) -> None:
        self.todos.set_active_project("other-app")
        # Simulate a fresh process reading the state file.
        self.assertEqual(self.todos.active_project(), "other-app")

    # ---- todo operations ----

    def test_add_creates_list_and_item(self) -> None:
        ok, _ = self.todos.add_todo("channel-cast", "fix the crash")
        self.assertTrue(ok)
        ok, body = self.todos.numbered_todos("channel-cast")
        self.assertIn("1. fix the crash", body)

    def test_numbered_only_shows_open_items(self) -> None:
        self.todos.add_todo("app", "first")
        self.todos.add_todo("app", "second")
        self.todos.complete_todo("app", 1)
        ok, body = self.todos.numbered_todos("app")
        # "first" is done, so "second" is now the only open item, numbered 1.
        self.assertIn("1. second", body)
        self.assertNotIn("first", body.split("done")[0])
        self.assertIn("1 done", body)

    def test_complete_renumbers_open_items(self) -> None:
        self.todos.add_todo("app", "a")
        self.todos.add_todo("app", "b")
        self.todos.add_todo("app", "c")
        # Completing #2 ("b") should leave "a" and "c" as 1 and 2.
        self.todos.complete_todo("app", 2)
        ok, body = self.todos.numbered_todos("app")
        self.assertIn("1. a", body)
        self.assertIn("2. c", body)
        self.assertNotIn("b", body.split("done")[0])

    def test_complete_out_of_range_is_rejected(self) -> None:
        self.todos.add_todo("app", "only")
        ok, msg = self.todos.complete_todo("app", 5)
        self.assertFalse(ok)
        self.assertIn("No open item #5", msg)

    def test_list_projects_reflects_created_lists(self) -> None:
        self.todos.add_todo("alpha", "x")
        self.todos.add_todo("beta", "y")
        self.assertEqual(self.todos.list_projects(), ["alpha", "beta"])

    def test_numbered_todos_missing_list_is_not_an_error(self) -> None:
        ok, body = self.todos.numbered_todos("never-created")
        self.assertTrue(ok)
        self.assertIn("no todo list", body.lower())


if __name__ == "__main__":
    unittest.main()
