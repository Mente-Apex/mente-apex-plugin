"""The operator's tree is never the mutation target.

mutmut materialises a mutants/ directory and Stryker a .stryker-tmp/; the prose
backend rewrites the artifact in place. All of it happens in a scratch copy, so
a dirty tree is safe and the operator can keep working during a sweep.
"""

import subprocess

import pytest

import mutation_gate_workspace
from mutation_gate_workspace import WorkspaceSetupError, scratch_workspace


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


@pytest.fixture
def plain_dir(tmp_path):
    """A directory with no git history at all -- not even `git init`."""
    (tmp_path / "money.py").write_text("VALUE = 1\n", encoding="utf-8")
    return tmp_path


def test_falls_back_to_a_plain_copy_when_there_is_no_git_repo(plain_dir):
    """Finding 3: the non-git fallback path was previously untested."""
    with scratch_workspace(plain_dir) as workspace:
        assert workspace != plain_dir
        assert (workspace / "money.py").read_text(encoding="utf-8") == "VALUE = 1\n"
        (workspace / "money.py").write_text("MUTATED = 0\n", encoding="utf-8")

    assert plain_dir.joinpath("money.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_plain_copy_fallback_also_cleans_up(plain_dir):
    """Finding 3: cleanup was previously only verified on the worktree path."""
    with scratch_workspace(plain_dir) as workspace:
        recorded = workspace

    assert not recorded.exists()


def test_setup_failure_does_not_leak_the_temp_directory(plain_dir, monkeypatch):
    """Finding 1: an exception raised while setting up the copy (before the
    try/finally is entered) must not orphan the mkdtemp-created directory.
    """
    created = {}
    real_mkdtemp = mutation_gate_workspace.tempfile.mkdtemp

    def recording_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created["parent"] = mutation_gate_workspace.Path(path)
        return path

    def failing_copytree(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(mutation_gate_workspace.tempfile, "mkdtemp", recording_mkdtemp)
    monkeypatch.setattr(mutation_gate_workspace.shutil, "copytree", failing_copytree)

    with pytest.raises(OSError), scratch_workspace(plain_dir):
        pass

    assert "parent" in created
    assert not created["parent"].exists()


def test_unexpected_git_failure_raises_instead_of_copying_the_dirty_tree(
    git_repo, monkeypatch
):
    """Finding 2: for an actual git repo, a worktree failure that is NOT
    "this isn't a git repository" must not silently degrade to the
    copytree fallback -- that would copy uncommitted edits instead of HEAD,
    diverging from the worktree path's semantics without telling anyone.
    """
    real_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "worktree", "add"]:
            return subprocess.CompletedProcess(
                cmd,
                returncode=128,
                stdout="",
                stderr="fatal: unable to create worktree\n",
            )
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(mutation_gate_workspace.subprocess, "run", fake_run)

    with pytest.raises(WorkspaceSetupError), scratch_workspace(git_repo):
        pass


def test_dirty_mode_copies_uncommitted_edits_and_untracked_files(git_repo):
    """Review round 1, Critical 1. `--scope working-tree` resolves its file
    list against the real working tree, but the default worktree-at-HEAD
    workspace cannot contain an uncommitted edit or an untracked file at all
    -- it is a clean checkout of HEAD by construction. dirty=True copies the
    working tree as it stands instead, so the files changed_paths() found are
    actually present to mutate.
    """
    (git_repo / "untracked.py").write_text("NEW = 1\n", encoding="utf-8")

    with scratch_workspace(git_repo, dirty=True) as workspace:
        assert (workspace / "money.py").read_text(encoding="utf-8") == "VALUE = 2\n"
        assert (workspace / "untracked.py").is_file()
        (workspace / "money.py").write_text("MUTATED = 1\n", encoding="utf-8")
        (workspace / "untracked.py").write_text("MUTATED = 1\n", encoding="utf-8")

    # the operator's tree stays byte-identical after the run
    assert git_repo.joinpath("money.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert git_repo.joinpath("untracked.py").read_text(encoding="utf-8") == "NEW = 1\n"


def test_dirty_mode_also_cleans_up(git_repo):
    with scratch_workspace(git_repo, dirty=True) as workspace:
        recorded = workspace

    assert not recorded.exists()


def test_worktree_mode_makes_an_installed_node_modules_reachable(git_repo):
    """Review round 1, Critical 2. `node_modules` is virtually always
    gitignored, so `git worktree add --detach HEAD` (tracked files only)
    never carries it into the isolated copy the default merge-base/full
    scope uses -- unlike the copytree fallback below (and dirty mode), which
    copies whatever is actually on disk and so already includes it. Without
    this, `StrykerBackend.available()` checks a workspace that can never see
    an already-installed Stryker (a false negative on every default-scope
    run against a repo that genuinely has it installed), and even with that
    check corrected, `npx stryker run` would have nothing to run against.
    """
    node_modules = git_repo / "node_modules" / "@stryker-mutator"
    node_modules.mkdir(parents=True)
    (node_modules / "core").mkdir()

    with scratch_workspace(git_repo) as workspace:
        assert (workspace / "node_modules" / "@stryker-mutator").is_dir()

    # the operator's real, gitignored node_modules is untouched by cleanup
    assert node_modules.is_dir()


def test_worktree_mode_without_node_modules_leaves_no_symlink(git_repo):
    with scratch_workspace(git_repo) as workspace:
        assert not (workspace / "node_modules").exists()


def test_copytree_fallback_already_carries_node_modules_without_a_symlink(plain_dir):
    """The copytree path (no git repo at all) copies whatever is on disk,
    `node_modules` included -- it needs no special-casing, only the worktree
    path (tracked files only) does.
    """
    node_modules = plain_dir / "node_modules" / "@stryker-mutator"
    node_modules.mkdir(parents=True)

    with scratch_workspace(plain_dir) as workspace:
        copied = workspace / "node_modules" / "@stryker-mutator"
        assert copied.is_dir()
        assert not copied.is_symlink()


def test_worktree_removal_failure_warns_instead_of_failing_silently(
    git_repo, monkeypatch
):
    """Finding 4: a failed `git worktree remove` must surface, not vanish
    into `ignore_errors=True`, so a stale registration is discoverable.
    """
    real_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "worktree", "remove"]:
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout="", stderr="fatal: could not remove\n"
            )
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(mutation_gate_workspace.subprocess, "run", fake_run)

    with pytest.warns(UserWarning, match="stale"), scratch_workspace(git_repo):
        pass


def test_the_non_git_case_is_detected_under_a_localized_git(tmp_path, monkeypatch):
    """`_try_worktree` distinguishes "not a git repository" (fall back to a
    copy) from any other git failure (raise) by matching git's ENGLISH stderr.
    Under a localized git that string never appears, so a plain directory would
    raise `WorkspaceSetupError` instead of falling back. Forcing `LC_ALL=C` on
    the calls whose stderr is parsed makes the message locale-independent.
    """
    import mutation_gate_workspace

    seen = {}
    real_run = subprocess.run

    def recording_run(argv, **kwargs):
        seen.update(kwargs.get("env") or {})
        return real_run(argv, **kwargs)

    monkeypatch.setattr(mutation_gate_workspace.subprocess, "run", recording_run)
    (tmp_path / "plain.txt").write_text("not a repo\n", encoding="utf-8")

    with scratch_workspace(tmp_path) as workspace:
        assert (workspace / "plain.txt").is_file()

    assert seen.get("LC_ALL") == "C"
