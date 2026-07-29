"""Isolation for mutation runs.

Every backend writes: mutmut materialises mutants/, Stryker .stryker-tmp/, and
the prose backend edits the artifact in place. The operator did not ask for any
of that in their tree, and their tree may be dirty, so runs happen in a copy.

A git worktree is preferred where `repo_root` is a git repository — it is
cheap and gives a clean checkout of HEAD. A plain copy of the working
directory is the fallback, used only when `repo_root` is not a git repository
at all. Any other git failure (missing binary, corrupt repo, disk full while
checking out) is treated as an error rather than silently degrading to a copy
of a possibly dirty tree, which would diverge from the worktree path's
"isolated copy at HEAD" contract without telling anyone.
"""

import shutil
import subprocess
import tempfile
import warnings
from contextlib import contextmanager
from pathlib import Path

_NOT_A_GIT_REPO = "not a git repository"


class WorkspaceSetupError(RuntimeError):
    """Raised when `scratch_workspace` cannot set up an isolated copy."""


def _try_worktree(repo_root, destination):
    """Add a detached worktree at HEAD.

    Returns True on success, False when `repo_root` is not a git repository
    at all (the expected case for the copytree fallback). Any other git
    failure raises `WorkspaceSetupError` instead of falling back silently.
    """
    result = subprocess.run(
        ["git", "worktree", "add", "--detach", "-q", str(destination), "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True
    if _NOT_A_GIT_REPO in result.stderr:
        return False
    raise WorkspaceSetupError(
        f"git worktree add failed for {repo_root}: {result.stderr.strip()}"
    )


def _remove_worktree(repo_root, destination):
    result = subprocess.run(
        ["git", "worktree", "remove", "--force", str(destination)],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        warnings.warn(
            f"git worktree remove failed for {destination}; a stale entry "
            f"may remain registered against {repo_root}: "
            f"{result.stderr.strip()}",
            stacklevel=2,
        )


@contextmanager
def scratch_workspace(repo_root, dirty=False):
    """Yield an isolated copy of `repo_root` for mutating, then clean it up.

    dirty=False (the default) copies HEAD, via a git worktree where possible
    -- cheap, and immune to whatever the operator's tree currently looks like.

    dirty=True copies the working tree exactly as it stands instead --
    uncommitted edits and untracked files included. `--scope working-tree`
    resolves its file list against the real tree, and a HEAD-only workspace
    cannot contain an uncommitted edit or an untracked file at all, by
    construction: mutating there would silently skip exactly the files the
    operator asked to sweep. Both modes exclude `.git` and `.venv`, and
    neither ever touches the operator's own tree -- the copy always lands in
    a fresh temp directory, never inside `repo_root` itself.
    """
    repo_root = Path(repo_root)
    parent = Path(tempfile.mkdtemp(prefix="mutation-gate-"))
    destination = parent / "workspace"
    used_worktree = False
    try:
        if dirty:
            shutil.copytree(
                repo_root, destination, ignore=shutil.ignore_patterns(".git", ".venv")
            )
        else:
            used_worktree = _try_worktree(repo_root, destination)
            if not used_worktree:
                shutil.copytree(
                    repo_root,
                    destination,
                    ignore=shutil.ignore_patterns(".git", ".venv"),
                )
    except BaseException:
        shutil.rmtree(parent, ignore_errors=True)
        raise
    try:
        yield destination
    finally:
        if used_worktree:
            _remove_worktree(repo_root, destination)
        shutil.rmtree(parent, ignore_errors=True)
