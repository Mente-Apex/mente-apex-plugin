"""Which branches the hook may call merged, against real git repositories.

Content alone cannot separate "merged" from "created and never committed to":
once a branch is merged it has no unique commits either. The first attempt at a
discriminator asked the reflog "did this branch ever carry a commit", which is
wrong in both directions -- a branch fetched from a remote reads
`branch: Created from refs/remotes/origin/X` and so looked like it had never
been committed to, silently suppressing every merge on the most common
multi-machine flow, while `reset`, `cherry-pick`, `merge` and `am` never
produce a subject beginning "commit" either.

These build real repositories rather than faking git, because the whole
question is what git actually writes.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import merged_branch  # noqa: E402


def run(*args, cwd):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def upstream(tmp_path):
    """A bare-ish origin with one commit on main."""
    origin = tmp_path / "origin"
    origin.mkdir()
    run("git", "init", "-q", "-b", "main", ".", cwd=origin)
    run("git", "config", "user.email", "t@e.st", cwd=origin)
    run("git", "config", "user.name", "T", cwd=origin)
    run("git", "commit", "-q", "--allow-empty", "-m", "init", cwd=origin)
    return origin


@pytest.fixture
def clone(tmp_path, upstream):
    work = tmp_path / "work"
    run("git", "clone", "-q", str(upstream), str(work), cwd=tmp_path)
    run("git", "config", "user.email", "t@e.st", cwd=work)
    run("git", "config", "user.name", "T", cwd=work)
    return work


def advance_upstream(upstream):
    """Somebody else pushes, so the remote default is no longer where it was."""
    run("git", "commit", "-q", "--allow-empty", "-m", "teammate", cwd=upstream)


def land_on_main(clone, upstream, branch, *, no_ff=True):
    """Merge `branch` into origin's main the way a PR would."""
    run("git", "push", "-q", "origin", f"{branch}:{branch}", cwd=clone)
    run("git", "checkout", "-q", "main", cwd=upstream)
    merge = [
        "git",
        "merge",
        "-q",
        "--no-ff" if no_ff else "--ff",
        branch,
        "-m",
        "merge",
    ]
    run(*merge, cwd=upstream)
    run("git", "fetch", "-q", "origin", cwd=clone)


def is_merged(clone, branch):
    return merged_branch.is_merged(clone, branch, "origin/main")


class TestABranchThatContributedNothingIsNotMerged:
    def test_a_freshly_created_branch_even_after_the_remote_moved(
        self, clone, upstream
    ):
        """The original false positive: the guard was `tip == tracking_tip`,
        which stops holding the moment a teammate pushes -- and the hook
        fetches immediately before checking."""
        run("git", "checkout", "-q", "-b", "feat/empty", cwd=clone)
        advance_upstream(upstream)
        run("git", "fetch", "-q", "origin", cwd=clone)

        assert is_merged(clone, "feat/empty") is False

    def test_it_is_not_offered_for_deletion_either(self, clone, upstream):
        """The same false positive reached the user through a second path:
        `merged_local_branches` kept its own copy of the `objectname ==
        tracking_tip` guard, so the branch the user was standing on was still
        listed as merged and safe to delete."""
        run("git", "checkout", "-q", "-b", "feat/empty", cwd=clone)
        advance_upstream(upstream)
        run("git", "fetch", "-q", "origin", cwd=clone)

        lines = merged_branch.report(clone)

        assert not any("feat/empty" in line for line in lines)


class TestARealMergeIsStillReported:
    def test_a_locally_created_branch_merged_with_a_merge_commit(self, clone, upstream):
        run("git", "checkout", "-q", "-b", "feat/work", cwd=clone)
        run("git", "commit", "-q", "--allow-empty", "-m", "work", cwd=clone)
        land_on_main(clone, upstream, "feat/work")

        assert is_merged(clone, "feat/work") is True

    def test_a_branch_fetched_from_the_remote(self, tmp_path, clone, upstream):
        """The regression: a branch obtained by clone/fetch reads
        `branch: Created from refs/remotes/origin/X`, which the reflog rule
        read as 'never committed to' -- suppressing every merge on the most
        common multi-machine flow."""
        run("git", "checkout", "-q", "-b", "feat/shared", cwd=clone)
        run("git", "commit", "-q", "--allow-empty", "-m", "work", cwd=clone)
        land_on_main(clone, upstream, "feat/shared")

        second = tmp_path / "second"
        run("git", "clone", "-q", str(upstream), str(second), cwd=tmp_path)
        run("git", "config", "user.email", "t@e.st", cwd=second)
        run("git", "config", "user.name", "T", cwd=second)
        run("git", "checkout", "-q", "feat/shared", cwd=second)

        assert is_merged(second, "feat/shared") is True

    def test_a_branch_advanced_by_reset_rather_than_commit(self, clone, upstream):
        """`reset: moving to X` does not begin with 'commit'."""
        run("git", "checkout", "-q", "-b", "source", cwd=clone)
        run("git", "commit", "-q", "--allow-empty", "-m", "work", cwd=clone)
        run("git", "checkout", "-q", "-b", "feat/reset", "main", cwd=clone)
        run("git", "reset", "-q", "--hard", "source", cwd=clone)
        land_on_main(clone, upstream, "feat/reset")

        assert is_merged(clone, "feat/reset") is True

    def test_a_branch_built_by_cherry_pick(self, clone, upstream):
        """`cherry-pick: msg` does not begin with 'commit' either."""
        run("git", "checkout", "-q", "-b", "source", cwd=clone)
        # A real change: cherry-picking an empty commit is refused by git.
        (clone / "picked.txt").write_text("content", encoding="utf-8")
        run("git", "add", "picked.txt", cwd=clone)
        run("git", "commit", "-q", "-m", "picked", cwd=clone)
        run("git", "checkout", "-q", "-b", "feat/pick", "main", cwd=clone)
        run("git", "cherry-pick", "source", cwd=clone)
        land_on_main(clone, upstream, "feat/pick")

        assert is_merged(clone, "feat/pick") is True

    def test_a_branch_whose_reflog_was_expired(self, clone, upstream):
        """No reflog means the question cannot be answered, and staying silent
        about real merges is the failure this hook exists to prevent -- so an
        unanswerable branch that IS an ancestor is reported."""
        run("git", "checkout", "-q", "-b", "feat/old", cwd=clone)
        run("git", "commit", "-q", "--allow-empty", "-m", "work", cwd=clone)
        land_on_main(clone, upstream, "feat/old")
        (clone / ".git" / "logs" / "refs" / "heads" / "feat" / "old").unlink()

        assert is_merged(clone, "feat/old") is True


class TestABranchNotOnMainIsNeverMerged:
    def test_an_unmerged_branch_with_its_own_commits(self, clone):
        run("git", "checkout", "-q", "-b", "feat/wip", cwd=clone)
        run("git", "commit", "-q", "--allow-empty", "-m", "wip", cwd=clone)

        assert is_merged(clone, "feat/wip") is False
