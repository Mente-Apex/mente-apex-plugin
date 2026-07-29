"""What the gate mutates by default.

Merge-base rather than working-tree, so a sweep does not change its answer as
the operator makes intermediate commits mid-audit. Full-repo mutation is far
too slow for an interactive skill, so it stays behind an explicit flag.
"""

import pytest

from mutation_gate import changed_paths


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
