"""Behaviour of the SessionStart merged-branch hook (#94).

Every test drives the real git CLI against a temp bare origin plus a clone.
Mocking git here would test our idea of git's exit codes rather than git's.
"""

import subprocess

import merged_branch
import pytest


def run(*args, cwd=None):
    """Run a command, failing the test loudly if it fails. Test setup only —
    the hook's own runner is deliberately silent, this one must not be."""
    completed = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    assert completed.returncode == 0, f"{args} failed: {completed.stderr}"
    return completed.stdout.strip()


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch, tmp_path):
    """Keep the author's real git identity, hooks, and aliases out of the temp
    repos. Without this the suite is green or red depending on whose machine
    it runs on."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig-none"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_path / "gitconfig-none"))
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")


@pytest.fixture
def clone(tmp_path):
    """A work tree on `main`, tracking a bare origin, with one pushed commit."""
    origin = tmp_path / "origin.git"
    run("git", "init", "--bare", "--initial-branch=main", str(origin))
    work = tmp_path / "work"
    run("git", "clone", str(origin), str(work))
    (work / "README.md").write_text("seed\n")
    run("git", "add", "README.md", cwd=work)
    run("git", "commit", "-m", "seed", cwd=work)
    run("git", "push", "-u", "origin", "main", cwd=work)
    return work


def test_git_runner_reports_failure_instead_of_raising(tmp_path):
    code, output = merged_branch.git(tmp_path, "rev-parse", "--git-dir")
    assert code != 0
    assert output == ""


def test_silent_outside_a_git_repository(tmp_path):
    assert merged_branch.report(tmp_path) == []


def test_silent_when_the_repository_has_no_remote(tmp_path):
    run("git", "init", "--initial-branch=main", str(tmp_path))
    (tmp_path / "a.txt").write_text("a\n")
    run("git", "add", "a.txt", cwd=tmp_path)
    run("git", "commit", "-m", "a", cwd=tmp_path)
    assert merged_branch.report(tmp_path) == []


def test_default_resolves_from_the_local_head_ref_on_a_clone(clone):
    assert merged_branch.resolve_default(clone, "origin") == "main"


def test_default_resolves_without_a_remote_head_ref(clone):
    # `git init` + `git remote add` never writes refs/remotes/<remote>/HEAD;
    # only a fresh clone does. Layer 1 must not be the only layer.
    run("git", "update-ref", "-d", "refs/remotes/origin/HEAD", cwd=clone)
    assert merged_branch.resolve_default(clone, "origin") == "main"


def test_default_is_none_when_no_layer_has_a_signal(tmp_path):
    run("git", "init", "--initial-branch=trunk", str(tmp_path))
    # No commits, no remote, and neither main nor master exists locally, so the
    # last-resort guess has nothing to offer either.
    assert merged_branch.resolve_default(tmp_path, "origin") is None


def test_current_branch_is_none_when_head_is_detached(clone):
    head = run("git", "rev-parse", "HEAD", cwd=clone)
    run("git", "checkout", "--detach", head, cwd=clone)
    assert merged_branch.current_branch(clone) is None


def test_silent_when_head_is_detached(clone):
    head = run("git", "rev-parse", "HEAD", cwd=clone)
    run("git", "checkout", "--detach", head, cwd=clone)
    assert merged_branch.report(clone) == []


def merge_into_main(clone, branch):
    """Merge `branch` into main on the origin, the way the GitHub UI would,
    leaving the clone still sitting on `branch` and unaware."""
    run("git", "checkout", "main", cwd=clone)
    run("git", "merge", "--no-ff", "-m", f"merge {branch}", branch, cwd=clone)
    run("git", "push", "origin", "main", cwd=clone)
    run("git", "checkout", branch, cwd=clone)
    # Rewind the local main so the clone looks like one that never pulled.
    run("git", "branch", "-f", "main", "main~1", cwd=clone)


def commit_on_new_branch(clone, branch, filename):
    run("git", "checkout", "-b", branch, cwd=clone)
    (clone / filename).write_text(filename)
    run("git", "add", filename, cwd=clone)
    run("git", "commit", "-m", f"add {filename}", cwd=clone)


def test_reports_the_merged_branch(clone):
    commit_on_new_branch(clone, "feat/x", "x.txt")
    merge_into_main(clone, "feat/x")
    assert "Branch feat/x has been merged into main." in merged_branch.report(clone)


def test_silent_on_an_unmerged_branch(clone):
    commit_on_new_branch(clone, "feat/x", "x.txt")
    assert merged_branch.report(clone) == []


def test_a_freshly_created_branch_is_not_merged(clone):
    # Its tip IS an ancestor of origin/main — it is origin/main. Calling that
    # "merged" would fire on every branch /ship has just created.
    run("git", "checkout", "-b", "feat/empty", cwd=clone)
    assert merged_branch.report(clone) == []


def test_silent_when_the_remote_tracking_ref_is_missing(clone):
    commit_on_new_branch(clone, "feat/x", "x.txt")
    run("git", "update-ref", "-d", "refs/remotes/origin/main", cwd=clone)
    run("git", "remote", "set-url", "origin", "/nonexistent/origin.git", cwd=clone)
    assert merged_branch.report(clone) == []


def test_unreachable_remote_does_not_raise(clone):
    commit_on_new_branch(clone, "feat/x", "x.txt")
    merge_into_main(clone, "feat/x")
    run("git", "remote", "set-url", "origin", "/nonexistent/origin.git", cwd=clone)
    # The fetch fails; the stale remote-tracking ref is still usable, and a
    # stale ref can only under-report a merge, never invent one.
    assert "Branch feat/x has been merged into main." in merged_branch.report(clone)


def test_reports_how_far_behind_the_local_default_is(clone):
    commit_on_new_branch(clone, "feat/x", "x.txt")
    merge_into_main(clone, "feat/x")
    assert "Local main is 2 commits behind origin/main." in merged_branch.report(clone)


def test_behind_line_is_the_only_line_on_a_stale_default_branch(clone):
    # Still on main, nothing merged, nothing lingering — one commit behind is
    # the whole story, and the singular reads correctly.
    (clone / "b.txt").write_text("b")
    run("git", "add", "b.txt", cwd=clone)
    run("git", "commit", "-m", "b", cwd=clone)
    run("git", "push", "origin", "main", cwd=clone)
    run("git", "reset", "--hard", "HEAD~1", cwd=clone)
    assert merged_branch.behind_count(clone, "main", "origin/main") == 1
    assert merged_branch.report(clone) == ["Local main is 1 commit behind origin/main."]


def test_silent_on_the_default_branch_when_it_is_current(clone):
    assert merged_branch.report(clone) == []
