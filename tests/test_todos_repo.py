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

    # ---- creation date and priority metadata ----

    def _path(self, project: str) -> Path:
        return self.repo / "projects" / project / "todo.md"

    def _write(self, project: str, text: str) -> None:
        self._path(project).parent.mkdir(parents=True, exist_ok=True)
        self._path(project).write_text(text)

    def test_parse_with_and_without_metadata(self) -> None:
        from ai_pm_agent import task_model

        content = (
            "- [ ] legacy\n"
            "- [ ] old structured <!-- pm-task:"
            f'{{"id":"{"a" * 32}","status":"open","priority":"high"}} -->\n'
            "- [ ] dated <!-- pm-task:"
            f'{{"id":"{"b" * 32}","status":"open","priority":"low",'
            '"created":"2026-10-01"} -->\n'
        )
        items = task_model.parse_items(content, "app")
        self.assertEqual(
            [(i["text"], i["created"], i["priority"]) for i in items],
            [
                ("legacy", None, "normal"),
                ("old structured", None, "high"),
                ("dated", "2026-10-01", "low"),
            ],
        )

    def test_invalid_created_date_is_rejected(self) -> None:
        from ai_pm_agent import task_model

        line = (
            f'- [ ] x <!-- pm-task:{{"id":"{"c" * 32}","status":"open",'
            '"priority":"normal","created":"2026-13-40"} -->\n'
        )
        with self.assertRaises(ValueError):
            task_model.parse_items(line, "app")

    def test_round_trip_keeps_metadata_exactly(self) -> None:
        from ai_pm_agent import task_model

        lines = (
            "# app\n\n"
            f'- [ ] dated <!-- pm-task:{{"id":"{"a" * 32}","status":"open",'
            '"priority":"high","created":"2026-10-01"} -->\n'
            f'- [ ] undated <!-- pm-task:{{"id":"{"b" * 32}","status":"open",'
            '"priority":"normal"} -->\n'
            f'- [ ] other <!-- pm-task:{{"id":"{"d" * 32}","status":"open",'
            '"priority":"normal"} -->\n'
        )
        self._write("app", lines)
        state = task_model.load(self.repo, "app")
        task_model.mutate(
            self.repo,
            "app",
            "update",
            {"id": "d" * 32, "revision": state["revision"], "status": "blocked"},
        )
        after = self._path("app").read_text()
        # Untouched lines, dated or not, are byte-identical after a rewrite.
        self.assertEqual(after.splitlines()[:4], lines.splitlines()[:4])

    def test_new_todo_gets_utc_creation_date(self) -> None:
        from datetime import date
        from unittest.mock import patch

        from ai_pm_agent import task_model

        self._write("app", "- [ ] legacy\n")
        with patch.object(task_model, "today", return_value=date(2026, 10, 15)):
            self.todos.add_todo("app", "fresh")
        self.assertEqual(
            [(i["text"], i["created"]) for i in self.todos.open_items("app")],
            [("legacy", None), ("fresh", "2026-10-15")],
        )
        self.assertIn('"created":"2026-10-15"', self._path("app").read_text())

    def test_edits_and_reorders_keep_dates_and_numbering(self) -> None:
        from datetime import date
        from unittest.mock import patch

        from ai_pm_agent import task_model

        for day, text in ((1, "first"), (2, "second"), (3, "third")):
            with patch.object(task_model, "today", return_value=date(2026, 10, day)):
                self.todos.add_todo("app", text)
        # The owner reorders lines by hand; dates travel with their lines.
        lines = self._path("app").read_text().splitlines()
        header, blank, first, second, third = lines
        self._write("app", "\n".join([header, blank, third, first, second]) + "\n")
        with patch.object(task_model, "today", return_value=date(2026, 12, 31)):
            self.todos.complete_todo("app", 2)
            state = task_model.load(self.repo, "app")
            task_model.mutate(
                self.repo,
                "app",
                "update",
                {
                    "id": state["items"][0]["id"],
                    "revision": state["revision"],
                    "text": "third, edited",
                    "priority": "high",
                },
            )
        self.assertEqual(
            self.todos.open_items("app"),
            [
                {
                    "index": 1,
                    "text": "third, edited",
                    "created": "2026-10-03",
                    "priority": "high",
                },
                {
                    "index": 2,
                    "text": "second",
                    "created": "2026-10-02",
                    "priority": "normal",
                },
            ],
        )
        done = task_model.load(self.repo, "app")["items"][1]
        self.assertEqual((done["status"], done["created"]), ("done", "2026-10-01"))

    def test_rendered_text_hides_metadata(self) -> None:
        self.todos.add_todo("app", "visible")
        _, body = self.todos.numbered_todos("app")
        self.assertEqual(body, "1. visible")
        self.assertEqual(self.todos.todo_summary("app")["open"], ["visible"])
        self.assertNotIn("<!--", self.todos.open_items("app")[0]["text"])


if __name__ == "__main__":
    unittest.main()
