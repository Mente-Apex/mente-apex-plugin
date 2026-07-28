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

import json
import os
import subprocess
import sys
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


def _default_from_gh(cwd: str | Path) -> str | None:
    """Layer 3: ask GitHub. Opportunistic — gh missing, unauthenticated, or
    pointed at a non-GitHub remote simply falls through to layer 4. This hook
    must work on a repo with no forge at all."""
    try:
        completed = subprocess.run(
            [
                "gh",
                "repo",
                "view",
                "--json",
                "defaultBranchRef",
                "-q",
                ".defaultBranchRef.name",
            ],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=NETWORK_TIMEOUT_SECONDS,
        )
    except OSError, subprocess.SubprocessError:
        return None
    return completed.stdout.strip() or None if completed.returncode == 0 else None


def resolve_default(cwd: str | Path, remote: str) -> str | None:
    """Four layers, cheapest first — the canonical ladder from
    docs/git-remote-resolution.md, transcribed into Python. The layer order is
    the point: layer 1 exists only on a fresh clone, so a repo built with
    `git init` + `git remote add` reaches the right answer only because the
    later layers run."""
    # 1. Local ref — instant, but only a freshly cloned repo has it.
    code, output = git(cwd, "symbolic-ref", f"refs/remotes/{remote}/HEAD")
    if code == 0 and output:
        return output.rsplit("/", 1)[-1]
    # 2. Ask the remote directly — a round-trip, always authoritative.
    code, output = git(cwd, "remote", "show", remote, timeout=NETWORK_TIMEOUT_SECONDS)
    if code == 0:
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("HEAD branch:"):
                name = stripped.split(":", 1)[1].strip()
                if name and name != "(unknown)":
                    return name
    # 3. Ask GitHub — works when the remote is unreachable but gh is authenticated.
    from_gh = _default_from_gh(cwd)
    if from_gh:
        return from_gh
    # 4. Guess from local branches, last resort.
    for candidate in ("main", "master"):
        code, _ = git(cwd, "show-ref", "--verify", "--quiet", f"refs/heads/{candidate}")
        if code == 0:
            return candidate
    return None


def current_branch(cwd: str | Path) -> str | None:
    """The checked-out branch, or None on a detached HEAD — where "the branch
    was merged" has no meaning."""
    code, output = git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD")
    return output if code == 0 and output else None


def is_merged(cwd: str | Path, revision: str, tracking: str) -> bool:
    """True when `revision` has landed on `tracking`.

    The tip comparison is not redundant with the ancestor check: a branch
    created a second ago and never committed to is an ancestor of the remote
    default because it *is* the remote default, and announcing that as a merge
    would fire on every branch /ship opens.
    """
    code_revision, tip = git(cwd, "rev-parse", revision)
    code_tracking, tracking_tip = git(cwd, "rev-parse", tracking)
    if code_revision != 0 or code_tracking != 0 or tip == tracking_tip:
        return False
    code, _ = git(cwd, "merge-base", "--is-ancestor", revision, tracking)
    return code == 0


def behind_count(cwd: str | Path, default: str, tracking: str) -> int:
    """How many commits the local default branch is behind the remote one.
    Zero when it is current, and zero when it does not exist locally at all —
    a repo you only ever work in on feature branches has nothing to pull."""
    code, output = git(cwd, "rev-list", "--count", f"{default}..{tracking}")
    if code != 0 or not output.isdigit():
        return 0
    return int(output)


def merged_local_branches(cwd: str | Path, default: str, tracking: str) -> list[str]:
    """Local branches that have landed on the remote default and are still
    sitting in refs/heads. Independent of HEAD on purpose: the branches that
    actually pile up are the ones you already switched away from."""
    code, output = git(cwd, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    if code != 0:
        return []
    return [
        branch
        for branch in output.splitlines()
        if branch != default and is_merged(cwd, branch, tracking)
    ]


def report(cwd: str | Path) -> list[str]:
    """The lines to inject as session context. Empty means stay silent."""
    code, _ = git(cwd, "rev-parse", "--git-dir")
    if code != 0:
        return []
    remote = resolve_remote(cwd)
    if remote is None:
        return []
    default = resolve_default(cwd, remote)
    if default is None:
        return []
    branch = current_branch(cwd)
    if branch is None:
        return []

    # One fetch of one branch. Failure is not fatal: a stale remote-tracking ref
    # can only miss a merge, never invent one.
    git(cwd, "fetch", "--quiet", remote, default, timeout=NETWORK_TIMEOUT_SECONDS)
    tracking = f"{remote}/{default}"
    code, _ = git(cwd, "rev-parse", "--verify", "--quiet", f"{tracking}^{{commit}}")
    if code != 0:
        return []

    lines = []
    if branch != default and is_merged(cwd, "HEAD", tracking):
        lines.append(f"Branch {branch} has been merged into {default}.")
    behind = behind_count(cwd, default, tracking)
    if behind:
        plural = "" if behind == 1 else "s"
        lines.append(f"Local {default} is {behind} commit{plural} behind {tracking}.")
    lingering = merged_local_branches(cwd, default, tracking)
    if lingering:
        lines.append(
            "Merged branches still present locally: " + ", ".join(lingering) + "."
        )
    return lines


def main() -> int:
    """Read the SessionStart payload, emit context only when there is some.

    Everything is inside one handler on purpose: a hook that raises at session
    start is strictly worse than a hook that says nothing, and there is no
    failure here worth interrupting the operator for.
    """
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        lines = report(payload.get("cwd") or os.getcwd())
        if lines:
            json.dump(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": "\n".join(lines),
                    }
                },
                sys.stdout,
            )
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
