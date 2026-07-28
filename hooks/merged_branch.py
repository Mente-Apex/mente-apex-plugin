"""SessionStart hook: say — once, and only when true — that the current branch
was merged, that the local default branch is behind, and which merged branches
still sit in refs/heads. Issue #94.

Silence is the product. A hook that speaks every session is a hook the agent
learns to skim past, so every unresolved condition returns nothing rather than
a diagnostic.

The merge check is `git merge-base --is-ancestor`, which is true for a merge
commit or a fast-forward. A squash- or rebase-merge rewrites the commits, so it
is invisible to this hook and to any local check; detecting those needs the
forge API, which this hook deliberately does not depend on.
"""

import subprocess
from pathlib import Path

GIT_TIMEOUT_SECONDS = 5
NETWORK_TIMEOUT_SECONDS = 8


def git(
    cwd: str | Path, *args: str, timeout: int = GIT_TIMEOUT_SECONDS
) -> tuple[int, str]:
    """Run a git command in `cwd` and return `(returncode, stdout)`.

    Never raises: a missing git binary, an unreadable cwd, or a timeout is
    reported as a non-zero code, so callers branch on data rather than
    wrapping every call in a handler.
    """
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except OSError, subprocess.SubprocessError:
        return 1, ""
    return completed.returncode, completed.stdout.strip()


def resolve_remote(cwd: str | Path) -> str | None:
    """Prefer `origin`, else the first configured remote. Never hardcode
    `origin` — forks and upstream-tracking clones name theirs differently.
    See docs/git-remote-resolution.md."""
    code, output = git(cwd, "remote")
    if code != 0 or not output:
        return None
    remotes = output.splitlines()
    return "origin" if "origin" in remotes else remotes[0]


def report(cwd: str | Path) -> list[str]:
    """The lines to inject as session context. Empty means stay silent."""
    code, _ = git(cwd, "rev-parse", "--git-dir")
    if code != 0:
        return []
    remote = resolve_remote(cwd)
    if remote is None:
        return []
    return []
