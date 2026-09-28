"""Verify markdown rule edits independently of Git synchronization."""

import pytest

from ai_pm_agent import config, rules_repo


@pytest.fixture
def rules_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RULES_REPO_PATH", str(tmp_path))
    (tmp_path / "global").mkdir()
    return tmp_path


def test_new_rule_file_is_created_under_global(rules_root):
    assert rules_repo.add_rule("python", "Use dataclasses")[0]
    assert (
        rules_root / "global/python.md"
    ).read_text() == "# python rules\n\n- Use dataclasses\n"


def test_numbered_rules_skip_headers_and_remove_only_selected_bullet(rules_root):
    path = rules_root / "global/python.md"
    path.write_text("# Rules\n\n- First\nSome context\n- Second\n")
    assert rules_repo.numbered_rules("python") == (True, "1. First\n2. Second")
    assert rules_repo.remove_rule("python", 1) == (True, "Removed: First")
    assert path.read_text() == "# Rules\n\nSome context\n- Second\n"


def test_missing_or_invalid_rule_number_does_not_change_file(rules_root):
    path = rules_root / "global/python.md"
    content = "# Rules\n- Keep me\n"
    path.write_text(content)
    assert not rules_repo.remove_rule("python", 2)[0]
    assert path.read_text() == content
    assert not rules_repo.read_rules("missing")[0]


def test_rule_counts_logs_unreadable_files(tmp_path, monkeypatch, caplog):
    from pathlib import Path

    from ai_pm_agent import config, rules_repo

    path = tmp_path / "rules.md"
    path.write_text("- rule\n")
    monkeypatch.setattr(config, "RULES_REPO_PATH", str(tmp_path))

    def unreadable(self, **kwargs):
        raise PermissionError("unreadable")

    monkeypatch.setattr(Path, "read_text", unreadable)

    assert rules_repo.rule_counts() == []
    assert "Could not count rules" in caplog.text
