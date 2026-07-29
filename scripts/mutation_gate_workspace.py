"""Isolation for mutation runs.

Every backend writes: mutmut materialises mutants/, Stryker .stryker-tmp/, and
the prose backend edits the artifact in place. The operator did not ask for any
of that in their tree, and their tree may be dirty, so runs happen in a copy.

A git worktree is preferred where the repo has one commit to anchor to — it is
cheap and gives a clean checkout. A plain copy is the fallback, so the gate
works in a directory that is not a git repo at all.
"""

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


def _try_worktree(repo_root, destination):
    """Add a detached worktree at HEAD. Returns True on success."""
    result = subprocess.run(
        ["git", "worktree", "add", "--detach", "-q", str(destination), "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _remove_worktree(repo_root, destination):
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(destination)],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )


@contextmanager
def scratch_workspace(repo_root):
    """Yield an isolated copy of `repo_root` for mutating, then clean it up."""
    repo_root = Path(repo_root)
    parent = Path(tempfile.mkdtemp(prefix="mutation-gate-"))
    destination = parent / "workspace"
    used_worktree = _try_worktree(repo_root, destination)
    if not used_worktree:
        shutil.copytree(
            repo_root, destination, ignore=shutil.ignore_patterns(".git", ".venv")
        )
    try:
        yield destination
    finally:
        if used_worktree:
            _remove_worktree(repo_root, destination)
        shutil.rmtree(parent, ignore_errors=True)
