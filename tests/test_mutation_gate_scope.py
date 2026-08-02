"""What the gate mutates by default.

Merge-base rather than working-tree, so a sweep does not change its answer as
the operator makes intermediate commits mid-audit. Full-repo mutation is far
too slow for an interactive skill, so it stays behind an explicit flag.
"""

import subprocess

import pytest

import mutation_gate_scope
from mutation_gate_scope import _parse_status_z, changed_paths


def test_merge_base_is_the_default_scope():
    import inspect

    signature = inspect.signature(changed_paths)
    assert signature.parameters["scope"].default == "merge-base"


def test_merge_base_scope_diffs_against_the_fork_point(git_repo_with_branch):
    repo, _ = git_repo_with_branch

    paths = changed_paths(repo, scope="merge-base")

    assert paths == ("feature.py",)


def test_working_tree_scope_sees_uncommitted_edits(git_repo_with_branch):
    repo, _ = git_repo_with_branch
    (repo / "scratch.py").write_text("x = 1\n", encoding="utf-8")

    paths = changed_paths(repo, scope="working-tree")

    assert "scratch.py" in paths


def test_an_unknown_scope_is_rejected(git_repo_with_branch):
    repo, _ = git_repo_with_branch

    with pytest.raises(ValueError, match="unknown scope"):
        changed_paths(repo, scope="everything-ever")


def test_working_tree_scope_survives_a_rename(git_repo_with_branch):
    """Review round 1, Critical 2. `git status --porcelain` (no -z) separates
    a rename with ` -> `, and line[3:] sliced the combined "old -> new" text
    as if it were one path -- a bogus string resolving to nothing on disk.
    """
    repo, _ = git_repo_with_branch
    subprocess.run(
        ["git", "mv", "feature.py", "renamed.py"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    paths = changed_paths(repo, scope="working-tree")

    assert "renamed.py" in paths
    assert not any("->" in path or "feature.py" in path for path in paths)


def test_working_tree_scope_survives_a_path_with_a_space(git_repo_with_branch):
    """Review round 1, Critical 2. Default porcelain quotes a path containing
    a space; line[3:] left the literal quote characters in the string, which
    then resolves to no file on disk.
    """
    repo, _ = git_repo_with_branch
    (repo / "space file.py").write_text("x = 1\n", encoding="utf-8")

    paths = changed_paths(repo, scope="working-tree")

    assert "space file.py" in paths
    assert not any('"' in path for path in paths)


def test_merge_base_scope_fails_loudly_when_the_default_branch_is_unknown(tmp_path):
    """Review round 1, Important. A repo whose default branch is neither main
    nor master (and has no origin/HEAD or usable init.defaultBranch) must not
    have `_default_branch` silently guess the alphabetically-first local
    branch -- that picks a wrong, unannounced fork point.
    """

    def run(*args):
        return subprocess.run(args, cwd=tmp_path, check=True, capture_output=True)

    run("git", "init", "-q", "-b", "develop")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "T")
    (tmp_path / "base.py").write_text("BASE = 1\n", encoding="utf-8")
    run("git", "add", ".")
    run("git", "commit", "-qm", "base")
    run("git", "checkout", "-qb", "feature")
    (tmp_path / "feature.py").write_text("FEATURE = 1\n", encoding="utf-8")
    run("git", "add", ".")
    run("git", "commit", "-qm", "feature")

    with pytest.raises(ValueError, match="default branch"):
        changed_paths(tmp_path, scope="merge-base")


def test_a_git_failure_names_the_cause_not_just_an_exit_code(tmp_path):
    """Review round 1, Important. `CalledProcessError.__str__` does not
    surface stderr, so a git failure must be re-raised with stderr attached
    or the operator cannot tell what actually went wrong.
    """
    with pytest.raises(RuntimeError, match="not a git repository"):
        changed_paths(tmp_path, scope="merge-base")


class TestADeletedFileIsNeverSelected:
    """A path that no longer exists cannot be mutated, and handing one to a
    backend as though it could poisons the run for every other file in the
    same partition: it becomes a `source_paths` entry naming a file absent
    from the workspace, and mutmut's loader breaks on it.
    """

    def test_a_working_tree_deletion_is_dropped(self):
        # `git rm b.py` stages a deletion: status "D " in the first column.
        assert _parse_status_z("D  b.py\0") == []

    def test_an_unstaged_deletion_is_dropped(self):
        # Deleted in the worktree but not staged: " D" in the second column.
        assert _parse_status_z(" D b.py\0") == []

    def test_an_ordinary_modification_is_still_selected(self):
        assert _parse_status_z(" M a.py\0") == ["a.py"]

    def test_a_rename_still_yields_the_new_path_only(self):
        # The old path is a second NUL-terminated field and no longer exists.
        assert _parse_status_z("R  new.py\0old.py\0") == ["new.py"]

    def test_the_merge_base_scope_asks_git_to_exclude_deletions(self, monkeypatch):
        """`--diff-filter=d` (lowercase: exclude) rather than filtering after
        the fact -- git already knows which paths the diff deleted."""
        captured = {}

        def fake_git(repo_root, *args, check=True):
            captured.setdefault("calls", []).append(args)
            if args[0] == "branch":
                return "main\n"
            if args[0] == "merge-base":
                return "abc123\n"
            return "a.py\0"

        monkeypatch.setattr(mutation_gate_scope, "_git", fake_git)

        mutation_gate_scope.changed_paths("/repo", scope="merge-base")

        diff_call = next(call for call in captured["calls"] if call[0] == "diff")
        assert "--diff-filter=d" in diff_call
