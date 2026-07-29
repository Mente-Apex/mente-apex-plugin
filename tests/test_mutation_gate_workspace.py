"""The operator's tree is never the mutation target.

mutmut materialises a mutants/ directory and Stryker a .stryker-tmp/; the prose
backend rewrites the artifact in place. All of it happens in a scratch copy, so
a dirty tree is safe and the operator can keep working during a sweep.
"""

import subprocess

import pytest

from mutation_gate_workspace import scratch_workspace


@pytest.fixture
def git_repo(tmp_path):
    """A one-commit git repo with an uncommitted edit, i.e. a dirty tree."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "money.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    (tmp_path / "money.py").write_text("VALUE = 2\n", encoding="utf-8")
    return tmp_path


def test_yields_a_writable_copy_that_is_not_the_original(git_repo):
    with scratch_workspace(git_repo) as workspace:
        assert workspace != git_repo
        assert (workspace / "money.py").is_file()
        (workspace / "money.py").write_text("MUTATED = 0\n", encoding="utf-8")

    assert git_repo.joinpath("money.py").read_text(encoding="utf-8") == "VALUE = 2\n"


def test_an_exception_inside_still_leaves_the_original_untouched(git_repo):
    before = (git_repo / "money.py").read_bytes()

    with pytest.raises(RuntimeError), scratch_workspace(git_repo) as workspace:
        (workspace / "money.py").write_text("MUTATED = 0\n", encoding="utf-8")
        raise RuntimeError("backend blew up mid-run")

    assert (git_repo / "money.py").read_bytes() == before


def test_cleans_up_after_itself(git_repo):
    with scratch_workspace(git_repo) as workspace:
        recorded = workspace

    assert not recorded.exists()
