# Merged-Branch SessionStart Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `SessionStart` hook that tells the agent, without being asked, that the
current branch was merged, that the local default branch is behind, and which merged
branches still linger locally — and that says nothing at all otherwise.

**Architecture:** One self-contained Python module, `hooks/merged_branch.py`, declared in
`hooks/hooks.json` and loaded natively by Claude Code from `${CLAUDE_PLUGIN_ROOT}`. Every
git call goes through one tolerant runner that returns `(returncode, stdout)` and never
raises, so each degradation path is a plain `if` rather than an exception handler. `report(cwd)`
returns a list of strings; `main()` is the only code that touches stdin, stdout, or the
process exit code. That split is what makes the whole thing testable against temp repos.

**Tech Stack:** Python 3.14 (uv-managed), pytest, `subprocess` + the `git` CLI. No third-party
dependencies, no `gh` dependency (layer 3 of the resolution ladder uses it opportunistically
and falls through when absent).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-28-merged-branch-hook-design.md`. Issue: #94.
- Silence is the default. Non-repo cwd, no remote, detached HEAD, unresolvable default
  branch, missing remote-tracking ref, nothing to report → no output, exit 0.
- Never raise out of the hook. Any unexpected exception exits 0 with no output.
- No `gh` requirement: `gh` missing, unauthenticated, or erroring must fall through, never fail.
- Never mutate the user's repo: no checkout, pull, delete, or `git remote set-head`. The only
  write is `git fetch` of one branch.
- Timeouts: 8s for the network calls (`fetch`, `remote show`, `gh`), 5s for local git calls.
- Python: run everything through `uv run` (never bare `python3` for the test suite).
- Formatting/lint: `uv run black .` and `uv run ruff check --fix .` before each commit;
  line-length 88.
- Version mirrors move together: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
  `pyproject.toml` — enforced by `tests/test_skill_integrity.py::test_version_mirrors_match`.
- Commit trailer on every commit: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Work happens on branch `feat/merged-branch-hook`, which already exists and already carries
  the design commit.

## File Structure

- **Create `hooks/merged_branch.py`** — the whole hook: git runner, remote/default resolution
  ladder, the three report lines, and `main()`.
- **Create `hooks/hooks.json`** — the `SessionStart` declaration, `${CLAUDE_PLUGIN_ROOT}`-relative.
- **Create `tests/test_merged_branch_hook.py`** — behavioural tests against real temp repos
  (bare origin + clone) plus the structural check on `hooks/hooks.json`.
- **Modify `tests/conftest.py`** — put `hooks/` on `sys.path` alongside `scripts/`.
- **Modify `docs/git-remote-resolution.md`** — add the hook to the consumer list and note that
  a Python transcription of the ladder lives there.
- **Modify `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`,
  `README.md`** — version bump to 0.22.0 and a line describing the hook.

---

### Task 1: Test harness and the tolerant git runner

**Files:**
- Create: `hooks/merged_branch.py`
- Create: `tests/test_merged_branch_hook.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `git(cwd: str | Path, *args: str, timeout: int = GIT_TIMEOUT_SECONDS) -> tuple[int, str]`
    — returns `(returncode, stdout.strip())`; a git that cannot even run returns `(1, "")`.
  - `report(cwd: str | Path) -> list[str]` — the lines to inject, empty when silent.
  - Test helpers `run(*args, cwd=None)` and the `clone` fixture (a work tree with a bare
    origin, one commit, `main` pushed and tracked).

- [ ] **Step 1: Put `hooks/` on the test path**

Append to `tests/conftest.py`, directly after the existing `sys.path.insert` for `scripts/`:

```python
# Make `import merged_branch` resolve to hooks/merged_branch.py — the hook ships
# in hooks/ because Claude Code loads a plugin's hooks from there, and like
# scripts/ it is a bare directory rather than an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_merged_branch_hook.py`:

```python
"""Behaviour of the SessionStart merged-branch hook (#94).

Every test drives the real git CLI against a temp bare origin plus a clone.
Mocking git here would test our idea of git's exit codes rather than git's.
"""

import os
import subprocess

import pytest

import merged_branch


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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'merged_branch'`.

- [ ] **Step 4: Write the minimal implementation**

Create `hooks/merged_branch.py`:

```python
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


def git(cwd: str | Path, *args: str, timeout: int = GIT_TIMEOUT_SECONDS) -> tuple[int, str]:
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
    except (OSError, subprocess.SubprocessError):
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: 3 passed.

- [ ] **Step 6: Format, lint, commit**

```bash
uv run black . && uv run ruff check --fix .
git add hooks/merged_branch.py tests/test_merged_branch_hook.py tests/conftest.py
git commit -m "feat(hook): add the tolerant git runner the merged-branch hook needs

A runner that reports failure as a returncode rather than an exception is
what lets every degradation path in this hook be an if rather than a
handler. Silence outside a repo and without a remote comes free with it.

Refs #94

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The remote/default resolution ladder

**Files:**
- Modify: `hooks/merged_branch.py`
- Test: `tests/test_merged_branch_hook.py`

**Interfaces:**
- Consumes: `git()`, `resolve_remote()` from Task 1.
- Produces:
  - `resolve_default(cwd, remote: str) -> str | None` — the default branch name, or `None`
    when no layer produced a signal.
  - `current_branch(cwd) -> str | None` — the checked-out branch, `None` when detached.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_merged_branch_hook.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: FAIL — `AttributeError: module 'merged_branch' has no attribute 'resolve_default'`.

- [ ] **Step 3: Write the implementation**

Add to `hooks/merged_branch.py`, above `report()`:

```python
def _default_from_gh(cwd: str | Path) -> str | None:
    """Layer 3: ask GitHub. Opportunistic — gh missing, unauthenticated, or
    pointed at a non-GitHub remote simply falls through to layer 4. This hook
    must work on a repo with no forge at all."""
    try:
        completed = subprocess.run(
            ["gh", "repo", "view", "--json", "defaultBranchRef", "-q",
             ".defaultBranchRef.name"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=NETWORK_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
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
```

Then extend `report()`, replacing its trailing `return []`:

```python
    default = resolve_default(cwd, remote)
    if default is None:
        return []
    branch = current_branch(cwd)
    if branch is None:
        return []
    return []
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: 8 passed.

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black . && uv run ruff check --fix .
git add hooks/merged_branch.py tests/test_merged_branch_hook.py
git commit -m "feat(hook): resolve the remote and default branch through the shared ladder

Layer 1 exists only on a freshly cloned repo, so the test that deletes
refs/remotes/origin/HEAD is the one that actually proves the ladder. gh is
layer 3 and stays optional: no forge, no auth, still resolves.

Refs #94

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: The merged-branch line

**Files:**
- Modify: `hooks/merged_branch.py`
- Test: `tests/test_merged_branch_hook.py`

**Interfaces:**
- Consumes: `git()`, `resolve_remote()`, `resolve_default()`, `current_branch()`.
- Produces: `is_merged(cwd, revision: str, tracking: str) -> bool` — true when `revision` is
  an ancestor of `tracking` **and** is not `tracking`'s own tip.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_merged_branch_hook.py`:

```python
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
    assert isinstance(merged_branch.report(clone), list)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: FAIL — `test_reports_the_merged_branch` gets `[]`.

- [ ] **Step 3: Write the implementation**

Add to `hooks/merged_branch.py`:

```python
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
```

Then extend `report()`, replacing its trailing `return []`:

```python
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
    return lines
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: 13 passed.

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black . && uv run ruff check --fix .
git add hooks/merged_branch.py tests/test_merged_branch_hook.py
git commit -m "feat(hook): detect the merged branch from the local ancestor check

No gh, no token, no rate limit: after one single-branch fetch, a merged
branch is one whose tip is an ancestor of the remote default. The tip
comparison keeps a freshly created branch from reading as merged.

Refs #94

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: The behind-count line

**Files:**
- Modify: `hooks/merged_branch.py`
- Test: `tests/test_merged_branch_hook.py`

**Interfaces:**
- Consumes: `git()`, `report()`.
- Produces: `behind_count(cwd, default: str, tracking: str) -> int` — 0 when the local default
  branch is current, absent, or unreadable.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_merged_branch_hook.py`:

```python
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
```

Note on `test_reports_how_far_behind_the_local_default_is`: the merge is a `--no-ff` merge,
so origin/main gains the feature commit **and** the merge commit — two commits ahead of the
rewound local main. The stale-default test pushes a plain fast-forward, hence one.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: FAIL — `AttributeError: module 'merged_branch' has no attribute 'behind_count'`.

- [ ] **Step 3: Write the implementation**

Add to `hooks/merged_branch.py`:

```python
def behind_count(cwd: str | Path, default: str, tracking: str) -> int:
    """How many commits the local default branch is behind the remote one.
    Zero when it is current, and zero when it does not exist locally at all —
    a repo you only ever work in on feature branches has nothing to pull."""
    code, output = git(cwd, "rev-list", "--count", f"{default}..{tracking}")
    if code != 0 or not output.isdigit():
        return 0
    return int(output)
```

Then extend `report()`, after the merged-branch block and before `return lines`:

```python
    behind = behind_count(cwd, default, tracking)
    if behind:
        plural = "" if behind == 1 else "s"
        lines.append(f"Local {default} is {behind} commit{plural} behind {tracking}.")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: 16 passed.

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black . && uv run ruff check --fix .
git add hooks/merged_branch.py tests/test_merged_branch_hook.py
git commit -m "feat(hook): report how far the local default branch has fallen behind

This is the line that turns the merge notice into an action: the agent
knows to pull rather than to ask. Absent local default counts as zero, so
a feature-branch-only clone stays silent.

Refs #94

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: The lingering-merged-branches line

**Files:**
- Modify: `hooks/merged_branch.py`
- Test: `tests/test_merged_branch_hook.py`

**Interfaces:**
- Consumes: `git()`, `is_merged()`, `report()`.
- Produces: `merged_local_branches(cwd, default: str, tracking: str) -> list[str]` — local
  branch names, excluding the default branch, that have landed on `tracking`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_merged_branch_hook.py`:

```python
def test_lists_merged_branches_that_still_exist_locally(clone):
    commit_on_new_branch(clone, "feat/x", "x.txt")
    merge_into_main(clone, "feat/x")
    lines = merged_branch.report(clone)
    assert "Merged branches still present locally: feat/x." in lines


def test_lists_lingering_branches_after_switching_back_to_the_default(clone):
    commit_on_new_branch(clone, "feat/x", "x.txt")
    merge_into_main(clone, "feat/x")
    run("git", "checkout", "main", cwd=clone)
    run("git", "merge", "--ff-only", "origin/main", cwd=clone)
    lines = merged_branch.report(clone)
    # Up to date and off the branch — the only thing left to say is cleanup.
    assert lines == ["Merged branches still present locally: feat/x."]


def test_the_default_branch_is_never_in_the_deletion_list(clone):
    assert merged_branch.merged_local_branches(clone, "main", "origin/main") == []


def test_lists_several_lingering_branches_in_ref_order(clone):
    commit_on_new_branch(clone, "feat/a", "a.txt")
    merge_into_main(clone, "feat/a")
    run("git", "checkout", "main", cwd=clone)
    run("git", "merge", "--ff-only", "origin/main", cwd=clone)
    commit_on_new_branch(clone, "feat/b", "b.txt")
    merge_into_main(clone, "feat/b")
    run("git", "checkout", "main", cwd=clone)
    run("git", "merge", "--ff-only", "origin/main", cwd=clone)
    assert merged_branch.merged_local_branches(clone, "main", "origin/main") == [
        "feat/a",
        "feat/b",
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: FAIL — `AttributeError: module 'merged_branch' has no attribute 'merged_local_branches'`.

- [ ] **Step 3: Write the implementation**

Add to `hooks/merged_branch.py`:

```python
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
```

Then extend `report()`, after the behind block and before `return lines`:

```python
    lingering = merged_local_branches(cwd, default, tracking)
    if lingering:
        lines.append(
            "Merged branches still present locally: " + ", ".join(lingering) + "."
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: 20 passed.

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black . && uv run ruff check --fix .
git add hooks/merged_branch.py tests/test_merged_branch_hook.py
git commit -m "feat(hook): list the merged branches still sitting in refs/heads

Deliberately independent of HEAD — the branches that accumulate are the
ones you already switched away from. The hook reports them; deleting stays
the operator's call.

Refs #94

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: `main()` — stdin, additionalContext, and unconditional exit 0

**Files:**
- Modify: `hooks/merged_branch.py`
- Test: `tests/test_merged_branch_hook.py`

**Interfaces:**
- Consumes: `report()`.
- Produces: `main() -> int` — reads the SessionStart payload on stdin, writes the
  `hookSpecificOutput` JSON to stdout when there is something to say, always returns 0.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_merged_branch_hook.py`:

```python
HOOK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(merged_branch.__file__))),
    "hooks",
    "merged_branch.py",
)


def invoke_hook(payload, cwd):
    """Run the hook as Claude Code runs it: a JSON payload on stdin."""
    return subprocess.run(
        [sys.executable, HOOK_PATH],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def test_hook_emits_additional_context_for_a_merged_branch(clone):
    commit_on_new_branch(clone, "feat/x", "x.txt")
    merge_into_main(clone, "feat/x")
    completed = invoke_hook({"cwd": str(clone)}, cwd=clone)
    assert completed.returncode == 0
    emitted = json.loads(completed.stdout)
    context = emitted["hookSpecificOutput"]["additionalContext"]
    assert emitted["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Branch feat/x has been merged into main." in context


def test_hook_emits_nothing_when_there_is_nothing_to_say(tmp_path):
    completed = invoke_hook({"cwd": str(tmp_path)}, cwd=tmp_path)
    assert completed.returncode == 0
    assert completed.stdout == ""


def test_hook_exits_silently_when_report_raises(monkeypatch, tmp_path):
    def explode(_cwd):
        raise RuntimeError("boom")

    monkeypatch.setattr(merged_branch, "report", explode)
    assert merged_branch.main() == 0


def test_hook_survives_malformed_stdin(tmp_path):
    completed = subprocess.run(
        [sys.executable, HOOK_PATH],
        input="not json",
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert completed.returncode == 0
    assert completed.stdout == ""
```

Add `import json` and `import sys` to the test module's imports.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: FAIL — the subprocess produces no stdout because there is no `__main__` entry point.

- [ ] **Step 3: Write the implementation**

Add to the end of `hooks/merged_branch.py`, and add `import json`, `import os`, `import sys`
to its imports:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: 24 passed.

- [ ] **Step 5: Commit**

```bash
uv run black . && uv run ruff check --fix .
git add hooks/merged_branch.py tests/test_merged_branch_hook.py
git commit -m "feat(hook): wire the report to SessionStart additionalContext

main() is the only code that touches stdin, stdout, or the exit code, and
it swallows everything: a hook that raises at session start is worse than
one that stays quiet.

Refs #94

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Declare the hook, document it, bump the version

**Files:**
- Create: `hooks/hooks.json`
- Modify: `tests/test_merged_branch_hook.py`
- Modify: `docs/git-remote-resolution.md`
- Modify: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`, `README.md`

**Interfaces:**
- Consumes: `hooks/merged_branch.py` from Tasks 1–6.
- Produces: the shipped declaration Claude Code loads; nothing further depends on it.

- [ ] **Step 1: Write the failing structural test**

Append to `tests/test_merged_branch_hook.py`:

```python
HOOKS_JSON = os.path.join(os.path.dirname(HOOK_PATH), "hooks.json")


def test_hooks_json_declares_the_hook_portably():
    declaration = json.loads(open(HOOKS_JSON).read())
    session_start = declaration["hooks"]["SessionStart"]
    commands = [
        hook["command"]
        for group in session_start
        for hook in group["hooks"]
    ]
    assert any("merged_branch.py" in command for command in commands)
    for command in commands:
        # An absolute path here works on exactly one machine.
        assert "${CLAUDE_PLUGIN_ROOT}" in command


def test_every_declared_hook_script_exists():
    declaration = json.loads(open(HOOKS_JSON).read())
    plugin_root = os.path.dirname(os.path.dirname(HOOKS_JSON))
    for groups in declaration["hooks"].values():
        for group in groups:
            for hook in group["hooks"]:
                relative = hook["command"].split("${CLAUDE_PLUGIN_ROOT}/", 1)[1]
                assert os.path.exists(os.path.join(plugin_root, relative)), relative
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: FAIL — `FileNotFoundError: hooks/hooks.json`.

- [ ] **Step 3: Create the declaration**

Create `hooks/hooks.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/merged_branch.py",
            "timeout": 10,
            "statusMessage": "Checking whether the branch was merged"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_merged_branch_hook.py -v`
Expected: 26 passed.

- [ ] **Step 5: Add the hook to the resolution doc's consumer list**

In `docs/git-remote-resolution.md`, replace the opening sentence:

```markdown
Shared by every skill in this plugin that pushes, targets a base branch, or checks
whether the working branch is current — today `/ship` (Step 1) and `/release` (Step 1).
```

with:

```markdown
Shared by every skill in this plugin that pushes, targets a base branch, or checks
whether the working branch is current — today `/ship` (Step 1), `/release` (Step 1), and
the SessionStart merged-branch hook. The hook is the one non-shell consumer: it carries a
Python transcription of the ladder in `hooks/merged_branch.py::resolve_default`, in the
same layer order, with layer 3 (`gh`) treated as optional. Change the ladder here and that
transcription changes with it.
```

- [ ] **Step 6: Bump the three version mirrors to 0.22.0**

```bash
sed -i '' 's/"version": "0.21.0"/"version": "0.22.0"/' .claude-plugin/plugin.json
sed -i '' 's/"version": "0.21.0"/"version": "0.22.0"/' .claude-plugin/marketplace.json
sed -i '' 's/^version = "0.21.0"/version = "0.22.0"/' pyproject.toml
```

- [ ] **Step 7: Document the hook in the README**

Add a short section to `README.md`, after the skills list, matching the file's existing tone:

```markdown
## Hooks

**SessionStart — merged-branch detector.** After a PR is merged in the forge UI, the plugin
injects one line of context so the agent knows without being told: that the current branch
has landed, how far the local default branch has fallen behind, and which merged branches
are still sitting in `refs/heads`. It runs one single-branch `git fetch` and is silent on a
clean repo, a non-repo directory, a detached HEAD, or an unmerged branch. Squash- and
rebase-merges rewrite commits and are invisible to the local ancestor check.
```

- [ ] **Step 8: Run the whole suite**

Run: `uv run pytest`
Expected: the full suite passes, including
`tests/test_skill_integrity.py::test_version_mirrors_match`.

- [ ] **Step 9: Commit**

```bash
uv run black . && uv run ruff check --fix .
git add hooks/hooks.json tests/test_merged_branch_hook.py docs/git-remote-resolution.md \
  .claude-plugin/plugin.json .claude-plugin/marketplace.json pyproject.toml README.md
git commit -m "feat(hook): ship the merged-branch detector as the plugin's first hook

hooks.json is ${CLAUDE_PLUGIN_ROOT}-relative and structurally tested, so an
absolute path that works on one machine cannot land. The resolution doc now
names its one Python consumer.

Closes #94

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Manual verification

The suite cannot prove the hook is actually loaded by Claude Code — only that it behaves.
After Task 7:

1. `/plugin` → update `mente-apex` (plugin changes do not reach live sessions otherwise).
2. Start a session in a repo whose branch was merged. Expect the context lines.
3. Start a session in `~` or another non-repo directory. Expect nothing, and no error.
