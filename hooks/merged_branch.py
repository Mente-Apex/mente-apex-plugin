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
import time
from pathlib import Path

GIT_TIMEOUT_SECONDS = 5
NETWORK_TIMEOUT_SECONDS = 8

# The per-call values above are ceilings, not a budget: seven of them in a row on
# a repo whose remote hangs adds up to far more than Claude Code will wait for.
# HOOK_TIMEOUT_SECONDS mirrors `timeout` in hooks/hooks.json — Claude Code kills
# the process at that mark — and TOTAL_BUDGET_SECONDS is what `report()` allows
# itself, deliberately under it so the hook finishes on its own terms and exits 0
# rather than being killed mid-run. tests/test_merged_branch_hook.py asserts both
# the mirror and the inequality, so the two numbers cannot drift apart again.
HOOK_TIMEOUT_SECONDS = 10
TOTAL_BUDGET_SECONDS = 8


class Deadline:
    """A wall clock shared by every subprocess one `report()` call makes.

    Passed explicitly rather than kept in a module global: the hook runs once per
    process, so a global would work, but a parameter is what makes a shrinking
    budget testable without monkeypatching module state between tests.
    """

    def __init__(self, budget: float = TOTAL_BUDGET_SECONDS) -> None:
        self._expiry = time.monotonic() + budget

    def remaining(self) -> float:
        return self._expiry - time.monotonic()

    def expired(self) -> bool:
        return self.remaining() <= 0

    def allow(self, ceiling: float) -> float:
        """The timeout for the next call: its own ceiling, or whatever is left."""
        return min(ceiling, self.remaining())


def _child_env() -> dict[str, str]:
    """The operator's environment, minus any way for a child to ask them a
    question. `subprocess.run(timeout=…)` kills the direct child only, so an
    `ssh` grandchild blocking on a passphrase prompt outlives every deadline we
    can set. Derived from `os.environ` because the calls still need PATH, HOME,
    and the user's git configuration."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    ssh = env.get("GIT_SSH_COMMAND") or "ssh"
    if "BatchMode" not in ssh:
        ssh = f"{ssh} -o BatchMode=yes"
    env["GIT_SSH_COMMAND"] = ssh
    return env


def _run(
    argv: list[str], cwd: str | Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    """The single place this hook spawns a process, so the no-prompt guarantee
    is structural rather than remembered at each call site."""
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_child_env(),
    )


def git(
    cwd: str | Path,
    *args: str,
    timeout: float = GIT_TIMEOUT_SECONDS,
    deadline: Deadline | None = None,
) -> tuple[int, str]:
    """Run a git command in `cwd` and return `(returncode, stdout)`.

    Never raises: a missing git binary, an unreadable cwd, or a timeout is
    reported as a non-zero code, so callers branch on data rather than
    wrapping every call in a handler. An exhausted `deadline` reads as one more
    failure, for the same reason.
    """
    allowance = timeout if deadline is None else deadline.allow(timeout)
    if allowance <= 0:
        return 1, ""
    try:
        completed = _run(["git", *args], cwd, allowance)
    except OSError, subprocess.SubprocessError:
        return 1, ""
    return completed.returncode, completed.stdout.strip()


def resolve_remote(cwd: str | Path, *, deadline: Deadline | None = None) -> str | None:
    """Prefer `origin`, else the first configured remote. Never hardcode
    `origin` — forks and upstream-tracking clones name theirs differently.
    See docs/git-remote-resolution.md."""
    code, output = git(cwd, "remote", deadline=deadline)
    if code != 0 or not output:
        return None
    remotes = output.splitlines()
    return "origin" if "origin" in remotes else remotes[0]


def _default_from_gh(
    cwd: str | Path, *, deadline: Deadline | None = None
) -> str | None:
    """Layer 3: ask GitHub. Opportunistic — gh missing, unauthenticated, or
    pointed at a non-GitHub remote simply falls through to layer 4. This hook
    must work on a repo with no forge at all."""
    allowance = (
        NETWORK_TIMEOUT_SECONDS
        if deadline is None
        else deadline.allow(NETWORK_TIMEOUT_SECONDS)
    )
    if allowance <= 0:
        return None
    try:
        completed = _run(
            [
                "gh",
                "repo",
                "view",
                "--json",
                "defaultBranchRef",
                "-q",
                ".defaultBranchRef.name",
            ],
            cwd,
            allowance,
        )
    except OSError, subprocess.SubprocessError:
        return None
    return completed.stdout.strip() or None if completed.returncode == 0 else None


def resolve_default(
    cwd: str | Path, remote: str, *, deadline: Deadline | None = None
) -> str | None:
    """Four layers, cheapest first — the canonical ladder from
    docs/git-remote-resolution.md, transcribed into Python. The layer order is
    the point: layer 1 exists only on a fresh clone, so a repo built with
    `git init` + `git remote add` reaches the right answer only because the
    later layers run."""
    # 1. Local ref — instant, but only a freshly cloned repo has it.
    code, output = git(
        cwd, "symbolic-ref", f"refs/remotes/{remote}/HEAD", deadline=deadline
    )
    if code == 0 and output:
        return output.rsplit("/", 1)[-1]
    # 2. Ask the remote directly — a round-trip, always authoritative.
    code, output = git(
        cwd,
        "remote",
        "show",
        remote,
        timeout=NETWORK_TIMEOUT_SECONDS,
        deadline=deadline,
    )
    if code == 0:
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("HEAD branch:"):
                name = stripped.split(":", 1)[1].strip()
                if name and name != "(unknown)":
                    return name
    # 3. Ask GitHub — works when the remote is unreachable but gh is authenticated.
    from_gh = _default_from_gh(cwd, deadline=deadline)
    if from_gh:
        return from_gh
    # 4. Guess from local branches, last resort.
    for candidate in ("main", "master"):
        code, _ = git(
            cwd,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{candidate}",
            deadline=deadline,
        )
        if code == 0:
            return candidate
    return None


def current_branch(cwd: str | Path, *, deadline: Deadline | None = None) -> str | None:
    """The checked-out branch, or None on a detached HEAD — where "the branch
    was merged" has no meaning."""
    code, output = git(
        cwd, "symbolic-ref", "--quiet", "--short", "HEAD", deadline=deadline
    )
    return output if code == 0 and output else None


def is_merged(
    cwd: str | Path, revision: str, tracking: str, *, deadline: Deadline | None = None
) -> bool:
    """True when `revision` has landed on `tracking`.

    The tip comparison is not redundant with the ancestor check: a branch
    created a second ago and never committed to is an ancestor of the remote
    default because it *is* the remote default, and announcing that as a merge
    would fire on every branch /ship opens.
    """
    code_revision, tip = git(cwd, "rev-parse", revision, deadline=deadline)
    code_tracking, tracking_tip = git(cwd, "rev-parse", tracking, deadline=deadline)
    if code_revision != 0 or code_tracking != 0 or tip == tracking_tip:
        return False
    code, _ = git(
        cwd, "merge-base", "--is-ancestor", revision, tracking, deadline=deadline
    )
    return code == 0


def behind_count(
    cwd: str | Path, default: str, tracking: str, *, deadline: Deadline | None = None
) -> int:
    """How many commits the local default branch is behind the remote one.
    Zero when it is current, and zero when it does not exist locally at all —
    a repo you only ever work in on feature branches has nothing to pull."""
    code, output = git(
        cwd, "rev-list", "--count", f"{default}..{tracking}", deadline=deadline
    )
    if code != 0 or not output.isdigit():
        return 0
    return int(output)


def merged_local_branches(
    cwd: str | Path, default: str, tracking: str, *, deadline: Deadline | None = None
) -> list[str]:
    """Local branches that have landed on the remote default and are still
    sitting in refs/heads. Independent of HEAD on purpose: the branches that
    actually pile up are the ones you already switched away from.

    Two subprocesses regardless of how many branches the repo has. Asking
    `is_merged` per branch was 2N+1 of them, which on a branch-heavy repo ate
    the budget the whole hook shares. `--merged` is the same ancestor test
    `merge-base --is-ancestor` performs, and printing the object name alongside
    the name preserves `is_merged`'s other half: a branch sitting exactly on the
    tracking tip has not been merged, it *is* the tip.
    """
    code, tracking_tip = git(cwd, "rev-parse", tracking, deadline=deadline)
    if code != 0:
        return []
    code, output = git(
        cwd,
        "for-each-ref",
        "--merged",
        tracking,
        "--format=%(objectname) %(refname:short)",
        "refs/heads",
        deadline=deadline,
    )
    if code != 0:
        return []
    lingering = []
    for line in output.splitlines():
        objectname, _, branch = line.partition(" ")
        if not branch or branch == default or objectname == tracking_tip:
            continue
        lingering.append(branch)
    return lingering


def report(cwd: str | Path, *, budget: float = TOTAL_BUDGET_SECONDS) -> list[str]:
    """The lines to inject as session context. Empty means stay silent.

    One deadline covers the whole call, so a repo whose remote hangs costs the
    budget once rather than once per network call.
    """
    deadline = Deadline(budget)
    code, _ = git(cwd, "rev-parse", "--git-dir", deadline=deadline)
    if code != 0:
        return []
    remote = resolve_remote(cwd, deadline=deadline)
    if remote is None:
        return []
    default = resolve_default(cwd, remote, deadline=deadline)
    if default is None:
        return []
    branch = current_branch(cwd, deadline=deadline)
    if branch is None:
        return []

    # One fetch of one branch. Failure is not fatal: a stale remote-tracking ref
    # can only miss a merge, never invent one.
    git(
        cwd,
        "fetch",
        "--quiet",
        remote,
        default,
        timeout=NETWORK_TIMEOUT_SECONDS,
        deadline=deadline,
    )
    # Everything from here is local and cheap, but a budget already spent means
    # the answer would be assembled from failed calls. Silence beats a half-truth.
    if deadline.expired():
        return []
    tracking = f"{remote}/{default}"
    code, _ = git(
        cwd,
        "rev-parse",
        "--verify",
        "--quiet",
        f"{tracking}^{{commit}}",
        deadline=deadline,
    )
    if code != 0:
        return []

    lines = []
    if branch != default and is_merged(cwd, "HEAD", tracking, deadline=deadline):
        lines.append(f"Branch {branch} has been merged into {default}.")
    behind = behind_count(cwd, default, tracking, deadline=deadline)
    if behind:
        plural = "" if behind == 1 else "s"
        lines.append(f"Local {default} is {behind} commit{plural} behind {tracking}.")
    lingering = merged_local_branches(cwd, default, tracking, deadline=deadline)
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
