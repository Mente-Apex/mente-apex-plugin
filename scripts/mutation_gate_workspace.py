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

import os
import shutil
import subprocess
import tempfile
import warnings
from contextlib import contextmanager
from pathlib import Path

_NOT_A_GIT_REPO = "not a git repository"

# Bounded like every other subprocess the gate starts. Adding or removing a
# worktree is local plumbing: quick, or stuck on a lock some crashed process
# still holds. An unbounded wait here hangs the gate before any mutation runs,
# and on teardown it would hang AFTER the results exist but before anything
# reports them.
GIT_TIMEOUT_SECONDS = 120


def _c_locale_env():
    """The process environment with git's output pinned to English.

    `_try_worktree` tells "not a git repository" (fall back to a copy) apart
    from every other git failure (raise) by matching git's stderr text. Under a
    localized git that message is translated, the match fails, and a plain
    non-git directory raises `WorkspaceSetupError` instead of falling back --
    the gate broken by nothing worse than the operator's LANG. `LC_ALL=C`
    makes the string we parse locale-independent.
    """
    return {**os.environ, "LC_ALL": "C"}


class WorkspaceSetupError(RuntimeError):
    """Raised when `scratch_workspace` cannot set up an isolated copy."""


def _try_worktree(repo_root, destination):
    """Add a detached worktree at HEAD.

    Returns True on success, False when `repo_root` is not a git repository
    at all (the expected case for the copytree fallback). Any other git
    failure raises `WorkspaceSetupError` instead of falling back silently.
    """
    try:
        result = subprocess.run(
            ["git", "worktree", "add", "--detach", "-q", str(destination), "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            env=_c_locale_env(),
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorkspaceSetupError(
            f"git worktree add did not finish within {GIT_TIMEOUT_SECONDS}s "
            f"for {repo_root}"
        ) from exc
    if result.returncode == 0:
        return True
    if _NOT_A_GIT_REPO in result.stderr:
        return False
    raise WorkspaceSetupError(
        f"git worktree add failed for {repo_root}: {result.stderr.strip()}"
    )


def _link_node_modules(repo_root, destination):
    """Make an already-installed JS toolchain reachable from a worktree copy.

    `node_modules` is virtually always gitignored, so `git worktree add`
    (tracked files only) never carries it into the isolated copy -- unlike
    the copytree fallback (and `dirty=True`), which copies whatever is
    actually on disk and so already includes it there. Without this,
    `StrykerBackend.available()` checks a workspace that can never see an
    already-installed Stryker (a false negative on every default-scope run
    against a repo that genuinely has it), and even a corrected check would
    leave `npx stryker run` with nothing to run against inside the worktree.

    A symlink, not a copy: there is nothing inside `node_modules` a mutation
    run needs to write, mirroring why `.venv` is excluded from the copytree
    path entirely rather than duplicated (Python resolves it via PATH
    regardless of cwd) -- `node_modules` just needs to exist at the expected
    relative location, and pointing at the real one is cheaper and always
    current. `shutil.rmtree` does not follow a symlinked directory when
    cleaning up the workspace afterwards, so the operator's real
    `node_modules` is never touched by teardown.

    CAVEAT, unproven and deliberately stated: teardown safety is verified, but
    nothing PREVENTS a tool invoked with `cwd=workspace` from writing THROUGH
    this symlink -- a plugin cache, npm reinstalling a peer dep -- which would
    breach the byte-identical guarantee for `node_modules` and only for
    `node_modules`. This repo has no JS project, so the path has never been
    exercised end to end by a real Stryker run. The guarantee therefore holds
    unconditionally for every other path in the tree and is UNVERIFIED here
    until a real JS audit exercises it. Do not restate it as unconditional in
    operator-facing prose while that is true.
    """
    source = Path(repo_root) / "node_modules"
    if source.is_dir():
        (Path(destination) / "node_modules").symlink_to(
            source, target_is_directory=True
        )


def _remove_worktree(repo_root, destination):
    """Unregister the scratch worktree, warning rather than raising on failure.

    Teardown runs in a `finally` after the results already exist, so a failure
    here must not replace them with an exception -- including a timeout, which
    is warned about for exactly the same reason a non-zero exit is.
    """
    try:
        result = subprocess.run(
            ["git", "worktree", "remove", "--force", str(destination)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        warnings.warn(
            f"git worktree remove did not finish within "
            f"{GIT_TIMEOUT_SECONDS}s for {destination}; a stale entry may "
            f"remain registered against {repo_root}",
            stacklevel=2,
        )
        return
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
            else:
                _link_node_modules(repo_root, destination)
    except BaseException:
        shutil.rmtree(parent, ignore_errors=True)
        raise
    try:
        yield destination
    finally:
        if used_worktree:
            _remove_worktree(repo_root, destination)
        shutil.rmtree(parent, ignore_errors=True)
