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


@pytest.mark.parametrize(
    "name",
    [
        "../",
        "../../tmp/x",
        r"global\python",
        "/tmp/x",
        r"C:\tmp\x",
        ".",
        "..",
        "",
        "_python",
        "-python",
        "a" * 81,
        "python\n",
        "two words",
        "pythön",
    ],
)
def test_unsafe_names_do_not_touch_files(tmp_path, monkeypatch, name):
    root = tmp_path / "rules"
    root.mkdir()
    existing = root / "keep.md"
    existing.write_text("- Keep me\n")
    monkeypatch.setattr(config, "RULES_REPO_PATH", str(root))
    before = sorted(tmp_path.rglob("*"))

    ok, message = rules_repo.add_rule(name, "Unsafe addition")

    assert not ok
    assert "Invalid rule name" in message
    assert sorted(tmp_path.rglob("*")) == before
    assert existing.read_text() == "- Keep me\n"


@pytest.mark.parametrize("name", ["a", "Python_3.12-rules", "a" * 80])
def test_valid_names_can_create_and_append(rules_root, name):
    assert rules_repo.add_rule(name, "First")[0]
    assert rules_repo.add_rule(name, "Second")[0]
    assert (rules_root / "global" / f"{name}.md").read_text() == (
        f"# {name} rules\n\n- First\n- Second\n"
    )


def test_append_existing_filename_without_final_newline(rules_root):
    path = rules_root / "global/python.md"
    path.write_text("- First")
    assert rules_repo.add_rule("python.md", "Second")[0]
    assert path.read_text() == "- First\n- Second\n"


@pytest.mark.parametrize(
    "kind", ["file", "directory", "dangling_file", "dangling_directory"]
)
def test_escaping_symlinks_do_not_change_files(tmp_path, monkeypatch, kind):
    root = tmp_path / "rules"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    kept = outside / "keep.md"
    kept.write_text("- Keep me\n")
    if "directory" in kind:
        target = outside if kind == "directory" else outside / "missing"
        (root / "global").symlink_to(target, target_is_directory=True)
    else:
        (root / "global").mkdir()
        target = kept if kind == "file" else outside / "missing.md"
        (root / "global/python.md").symlink_to(target)
    monkeypatch.setattr(config, "RULES_REPO_PATH", str(root))
    before = sorted(tmp_path.rglob("*"))

    ok, message = rules_repo.add_rule("python", "Unsafe addition")

    assert not ok
    assert "outside the rules repository" in message
    assert sorted(tmp_path.rglob("*")) == before
    assert kept.read_text() == "- Keep me\n"


def test_escaping_file_is_not_read_counted_or_removed(tmp_path, monkeypatch):
    root = tmp_path / "rules"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("- Keep me\n")
    (root / "python.md").symlink_to(outside)
    monkeypatch.setattr(config, "RULES_REPO_PATH", str(root))

    assert not rules_repo.read_rules("python")[0]
    assert not rules_repo.remove_rule("python", 1)[0]
    assert rules_repo.rule_counts() == []
    assert outside.read_text() == "- Keep me\n"


def test_repository_root_and_internal_symlinks_are_resolved(tmp_path, monkeypatch):
    root = tmp_path / "rules"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    target = root / "actual.md"
    target.write_text("- First\n")
    (root / "python.md").symlink_to(target)
    monkeypatch.setattr(config, "RULES_REPO_PATH", str(alias))

    assert rules_repo.add_rule("python", "Second")[0]
    assert target.read_text() == "- First\n- Second\n"
    assert rules_repo.add_rule("new", "Created")[0]
    assert (root / "global/new.md").read_text() == "# new rules\n\n- Created\n"


@pytest.fixture
def duplicate_rules(rules_root):
    paths = [rules_root / "projects/demo/python.md", rules_root / "global/python.md"]
    for index, path in enumerate(paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"# Rules {index}\r\n- Keep {index}\r\n".encode())
    return paths


@pytest.mark.parametrize("name", ["python", "python.md", "PYTHON", "PYTHON.MD"])
def test_ambiguous_selectors_never_edit_or_create(rules_root, duplicate_rules, name):
    before = {path: path.read_bytes() for path in duplicate_rules}
    files = sorted(rules_root.rglob("*"))
    for result in (
        rules_repo.read_rules(name),
        rules_repo.numbered_rules(name),
        rules_repo.add_rule(name, "Do not add"),
        rules_repo.remove_rule(name, 1),
    ):
        ok, message = result
        assert not ok
        assert "Ambiguous rule file" in message
        assert message.splitlines()[1:] == [
            "global/python.md",
            "projects/demo/python.md",
        ]
        assert {path: path.read_bytes() for path in duplicate_rules} == before
        assert sorted(rules_root.rglob("*")) == files


@pytest.mark.parametrize(
    "selector",
    ["projects/demo/python.md", "PROJECTS/DEMO/PYTHON", "projects/demo/python"],
)
def test_relative_selectors_target_only_selected_file(
    rules_root, duplicate_rules, selector
):
    target, other = duplicate_rules
    unchanged = other.read_bytes()
    assert rules_repo.read_rules(selector)[0]
    assert rules_repo.add_rule(selector, "Added")[0]
    assert rules_repo.remove_rule(selector, 1) == (True, "Removed: Keep 0")
    assert target.read_text() == "# Rules 0\n- Added\n"
    assert other.read_bytes() == unchanged


def test_exact_root_filename_wins_over_shorthand(rules_root, duplicate_rules):
    root_file = rules_root / "python.md"
    root_file.write_text("- Root\n")
    before = [path.read_bytes() for path in duplicate_rules]
    assert rules_repo.read_rules("python.md") == (True, "- Root\n")
    assert rules_repo.add_rule("python.md", "Added")[0]
    assert rules_repo.remove_rule("python.md", 1) == (True, "Removed: Root")
    assert root_file.read_text() == "- Added\n"
    assert [path.read_bytes() for path in duplicate_rules] == before


@pytest.mark.parametrize("selector", ["PYTHON", "PYTHON.MD", "global/PYTHON"])
def test_unique_case_insensitive_shorthand(rules_root, selector):
    path = rules_root / "global/python.md"
    path.write_text("- First\n")
    assert rules_repo.read_rules(selector) == (True, "- First\n")
    assert rules_repo.add_rule(selector, "Second")[0]
    assert rules_repo.remove_rule(selector, 1)[0]
    assert path.read_text() == "- Second\n"


@pytest.mark.parametrize(
    "selector", ["global/missing", "global/missing.md", "missing/python.md"]
)
def test_missing_relative_selectors_do_not_create_files(rules_root, selector):
    before = sorted(rules_root.rglob("*"))
    for result in (
        rules_repo.read_rules(selector),
        rules_repo.add_rule(selector, "New"),
        rules_repo.remove_rule(selector, 1),
    ):
        assert not result[0]
        assert "No rule file matching" in result[1]
    assert sorted(rules_root.rglob("*")) == before


@pytest.mark.parametrize(
    "selector",
    [
        "../python.md",
        "global/../python.md",
        "/python.md",
        "global//python.md",
        "./python.md",
        "global/python.md/",
    ],
)
def test_unsafe_selectors_rejected_for_all_operations(rules_root, selector):
    path = rules_root / "python.md"
    path.write_bytes(b"- Keep\r\n")
    for result in (
        rules_repo.read_rules(selector),
        rules_repo.add_rule(selector, "New"),
        rules_repo.remove_rule(selector, 1),
    ):
        assert not result[0]
        assert "Invalid rule name" in result[1]
    assert path.read_bytes() == b"- Keep\r\n"


@pytest.mark.parametrize("internal", [True, False])
def test_exact_relative_symlink_containment(rules_root, tmp_path, internal):
    target = (rules_root if internal else rules_root.parent) / "target-rules.md"
    target.write_text("- Keep\n")
    (rules_root / "global/link.md").symlink_to(target)
    selector = "global/link.md"
    assert rules_repo.read_rules(selector)[0] is internal
    assert rules_repo.add_rule(selector, "New")[0] is internal
    assert rules_repo.remove_rule(selector, 1)[0] is internal
    assert target.read_text() == ("- New\n" if internal else "- Keep\n")
