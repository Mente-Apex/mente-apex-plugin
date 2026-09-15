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


def forge_merged_branches(
    cwd: str | Path, *, limit: int = 50, deadline: Deadline | None = None
) -> frozenset[str]:
    """Head-ref names the forge reports as merged. Empty when it cannot say.

    The second source of the merged signal, and the only one that can see a
    squash or rebase merge: those rewrite the branch's commits, so its tip is
    not an ancestor of the default and `merge-base --is-ancestor` is false
    forever (issue #108). This repo has all three merge methods enabled and the
    very first real merge took a path the hook could not see.

    Opportunistic in exactly the way `_default_from_gh` is: gh missing,
    unauthenticated, pointed at a non-GitHub remote, rate-limited or simply
    slow all arrive at the caller as an empty set, and an empty set changes
    nothing. There is no hard dependency on a forge, and silence stays the
    default.

    ONE call for every branch, not one per branch. The batched consumer
    (`merged_local_branches`) runs over every local ref, and a network round
    trip each would eat the whole hook's budget on a branch-heavy repo -- the
    same reason that function uses two subprocesses regardless of branch count.
    """
    allowance = (
        NETWORK_TIMEOUT_SECONDS
        if deadline is None
        else deadline.allow(NETWORK_TIMEOUT_SECONDS)
    )
    if allowance <= 0:
        return frozenset()
    try:
        completed = _run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "merged",
                "--limit",
                str(limit),
                "--json",
                "headRefName",
                "-q",
                ".[].headRefName",
            ],
            cwd,
            allowance,
        )
    except OSError, subprocess.SubprocessError:
        return frozenset()
    if completed.returncode != 0:
        return frozenset()
    return frozenset(
        line.strip() for line in completed.stdout.splitlines() if line.strip()
    )


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
        # Strip the `refs/remotes/<remote>/` PREFIX, never `rsplit("/")`. The
        # ref is `refs/remotes/origin/release/2.0` for a default branch with a
        # slash in its name, and taking the last segment yielded `2.0` — a
        # branch that does not exist, so `tracking` never verified and this
        # hook went permanently silent on every such repo.
        prefix = f"refs/remotes/{remote}/"
        if output.startswith(prefix):
            return output[len(prefix) :]
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
    cwd: str | Path,
    revision: str,
    tracking: str,
    *,
    forge_merged: frozenset[str] = frozenset(),
    deadline: Deadline | None = None,
) -> bool:
    """True when `revision` has landed on `tracking`.

    Being an ancestor of tracking is necessary but not sufficient: a branch
    created a second ago and never committed to is an ancestor too, because it
    still points at a commit tracking already had. Announcing that would fire
    on every branch /ship opens.

    Content alone cannot separate the two — once a branch is merged, it has no
    unique commits either — so two cheap facts stand in, in order:

    1. Does the branch exist on the remote? Then it was published, and an
       ancestor of tracking means it landed. This is what makes the ordinary
       multi-machine flow work: a branch obtained by clone or fetch has no
       local history at all, and asking its reflog anything is meaningless.
    2. Otherwise, has the branch moved since it was created here? Its reflog
       answers that directly. Created-and-never-moved contributed nothing.

    The previous guard was `tip == tracking_tip`, which holds only for as long
    as the remote default has not moved. This hook fetches immediately before
    checking, so the moment a teammate pushed anything, a freshly created
    branch stopped equalling the tip, passed the ancestor check, and was
    announced as merged and listed as safe to delete — the branch the user was
    standing on. It was also wrong in the other direction: a branch merged
    fast-forward with nothing pushed since DID equal the tip, and a real merge
    went unreported.

    The replacement attempt — "does the reflog contain a `commit:` entry" —
    was wrong in both directions too, and is what step 2 below corrects. A
    fetched branch reads `branch: Created from refs/remotes/origin/X`, so every
    merge on a second machine was silently suppressed; and `reset:`,
    `cherry-pick:`, `merge X:` and `am:` are all ways a branch legitimately
    acquires commits without any subject beginning "commit". Asking whether the
    branch MOVED, rather than how, is indifferent to which of those happened.
    """
    code_revision, _ = git(cwd, "rev-parse", revision, deadline=deadline)
    code_tracking, _ = git(cwd, "rev-parse", tracking, deadline=deadline)
    if code_revision != 0 or code_tracking != 0:
        return False
    code, _ = git(
        cwd, "merge-base", "--is-ancestor", revision, tracking, deadline=deadline
    )
    if code != 0:
        # Not an ancestor. Under merge-commit that settles it; under a squash or
        # rebase merge it settles nothing, because the branch's commits were
        # rewritten (issue #108). The forge is the only thing that can tell those
        # apart -- but it answers with head-ref NAMES, not commits, and names get
        # reused: `fix/login` merged in March and recreated in September is a
        # different branch wearing a merged name, and fork PRs make `patch-1`,
        # `develop` and `master` routine entries in that set.
        #
        # So the name is necessary and not sufficient, and the same two questions
        # that qualify an ancestor qualify it here: was this branch published, or
        # has it moved since it was created? A recreated name has neither, and
        # announcing it would list the branch the user is standing on as safe to
        # delete.
        if revision not in forge_merged:
            return False
        remote_for_forge = tracking.split("/", 1)[0]
        if _exists_on_remote(cwd, revision, remote_for_forge, deadline=deadline):
            return True
        return not _created_and_never_moved(cwd, revision, deadline=deadline)
    remote = tracking.split("/", 1)[0]
    if _exists_on_remote(cwd, revision, remote, deadline=deadline):
        return True
    return not _created_and_never_moved(cwd, revision, deadline=deadline)


def _exists_on_remote(
    cwd: str | Path, revision: str, remote: str, *, deadline: Deadline | None = None
) -> bool:
    """Does `remote` carry a branch of this name?

    A published branch was shared deliberately, so an ancestor of tracking is a
    branch that landed — no local history needed, which is exactly the case the
    reflog cannot speak to.
    """
    code, _ = git(
        cwd,
        "show-ref",
        "--verify",
        "--quiet",
        f"refs/remotes/{remote}/{revision}",
        deadline=deadline,
    )
    return code == 0


def _created_and_never_moved(
    cwd: str | Path, revision: str, *, deadline: Deadline | None = None
) -> bool:
    """True only when this branch was created here and has not moved since.

    Exactly one reflog entry, and that entry a creation. Every way a branch
    acquires commits — commit, amend, reset, cherry-pick, merge, am, rebase —
    appends an entry, so "one entry, and it is the creation" is the one shape
    that means "contributed nothing", without this function needing to know the
    vocabulary of subjects git might write.

    False when there is no reflog to read (expired, or a ref that never had
    one): the question cannot be answered, and staying silent about a real
    merge is the failure this hook exists to prevent, so the unanswerable case
    does not suppress.
    """
    code, output = git(
        cwd, "reflog", "show", "--format=%gs", revision, deadline=deadline
    )
    if code != 0 or not output:
        return False
    entries = output.splitlines()
    return len(entries) == 1 and entries[0].startswith("branch: Created from")


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
    cwd: str | Path,
    default: str,
    tracking: str,
    *,
    exclude: tuple = (),
    forge_merged: frozenset[str] = frozenset(),
    deadline: Deadline | None = None,
) -> list[str]:
    """Local branches that have landed on the remote default and are still
    sitting in refs/heads. The branches that actually pile up are the ones you
    already switched away from.

    Two subprocesses regardless of how many branches the repo has. Asking
    `is_merged` per branch was 2N+1 of them, which on a branch-heavy repo ate
    the budget the whole hook shares. `--merged` is the same ancestor test
    `merge-base --is-ancestor` performs.

    `exclude` names branches the caller has already judged more carefully than
    this batched test can. The `objectname == tracking_tip` guard below is the
    same one `is_merged` had to abandon — it stops holding as soon as the
    remote default advances — so a branch created a moment ago and never
    committed to was listed here as merged and deletable, which is the original
    false positive arriving by a second route. Rather than spend a reflog
    subprocess per branch and lose the batching this function exists for,
    `report` passes the one branch it has already checked properly.

    A non-current branch with no commits of its own may still be listed, and
    that is honest: everything it points at is already on the default, so
    deleting it loses nothing.
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
    seen = set()
    for line in output.splitlines():
        objectname, _, branch = line.partition(" ")
        if not branch or branch == default or branch in exclude:
            continue
        # ADJUDICATED, not reported. This set records every ref the batched pass
        # has already ruled on, so the forge pass below cannot re-add one it
        # deliberately skipped: a freshly recreated branch sitting at the
        # tracking tip is exactly the false positive the guard above exists to
        # stop, and re-adding it by a second route is how that bug came back.
        seen.add(branch)
        if objectname == tracking_tip:
            continue
        lingering.append(branch)

    # The ancestor test above cannot see a squash- or rebase-merged branch, so
    # one accumulated in refs/heads permanently -- the precise opposite of what
    # this line exists to do (issue #108). A second pass over the forge's answer
    # recovers exactly those, and only for refs that still exist locally: the
    # forge lists every merged head ref in the repository, including branches
    # this machine has never had.
    for branch in sorted(forge_merged):
        if branch in seen or branch == default or branch in exclude:
            continue
        code, _ = git(
            cwd,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
            deadline=deadline,
        )
        if code == 0:
            lingering.append(branch)
    return lingering


def report(
    cwd: str | Path,
    *,
    budget: float = TOTAL_BUDGET_SECONDS,
    forge_merged: frozenset[str] | None = None,
) -> list[str]:
    """The lines to inject as session context. Empty means stay silent.

    One deadline covers the whole call, so a repo whose remote hangs costs the
    budget once rather than once per network call.

    This is where the two merged signals are composed: the forge answer is
    fetched ONCE here and handed to both consumers, so neither of them knows
    anything about gh, GitHub, or networks -- they take a set of branch names.
    `forge_merged` is injectable for the same reason: a test says what the forge
    said without a forge, and a caller that already knows can skip the call.
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
    # The branch by name, not "HEAD". They resolve to the same commit while it
    # is checked out, but only the branch has a reflog of its own -- HEAD's is
    # the whole session's checkout history, which says nothing about this
    # branch. See `_created_and_never_moved`.
    if forge_merged is None:
        forge_merged = forge_merged_branches(cwd, deadline=deadline)
    current_is_merged = branch != default and is_merged(
        cwd, branch, tracking, forge_merged=forge_merged, deadline=deadline
    )
    if current_is_merged:
        lines.append(f"Branch {branch} has been merged into {default}.")
    behind = behind_count(cwd, default, tracking, deadline=deadline)
    if behind:
        plural = "" if behind == 1 else "s"
        lines.append(f"Local {default} is {behind} commit{plural} behind {tracking}.")
    # The checked-out branch is withheld from the deletion list ONLY when the
    # careful check above says it is not merged. `merged_local_branches` uses a
    # cheap batched ancestor test that cannot tell a freshly created branch
    # from a landed one, and that gap was the original false positive arriving
    # by a second route. A current branch that genuinely IS merged still
    # appears, which is what the existing behaviour promises.
    lingering = merged_local_branches(
        cwd,
        default,
        tracking,
        exclude=() if current_is_merged else (branch,),
        forge_merged=forge_merged,
        deadline=deadline,
    )
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
