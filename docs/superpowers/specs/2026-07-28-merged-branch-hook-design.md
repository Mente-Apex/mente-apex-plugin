# SessionStart merged-branch hook — design

Issue: #94. Depends on #93 only for `docs/git-remote-resolution.md`, which is now in place.

## Problem

After `/ship` opens a PR and a human merges it in the GitHub UI, the agent has no idea.
Every session after a merge starts with the operator typing some variant of "I merged that
PR". That is a fact the agent can determine for itself, and stating it is pure friction —
repeated across every repo, every merge.

The signal is local. A merged branch is one whose commits are ancestors of the remote
default branch; after a single-branch fetch that is a pure local check — no `gh`, no API
token, no rate limit.

## Placement

A new `hooks/` directory at the repo root:

- `hooks/hooks.json` — the declaration.
- `hooks/merged_branch.py` — the hook.

Registered on `SessionStart` as `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/merged_branch.py`
with `timeout: 10`. Claude Code loads a plugin's `hooks.json` natively, so the hook
activates wherever the plugin is installed — no `settings.json` edit and no config-sync
root token. This is the plugin's first shipped hook.

Operational caveat, not a design flaw: plugin changes do not reach live sessions until an
interactive `/plugin` update.

## Behaviour

Silent unless there is something to say. A hook that speaks every session gets ignored.

The hook reads the SessionStart JSON on stdin for `cwd` and works from that directory.

1. **Bail silently** on: a non-repo cwd, a repo with no remote, or a detached HEAD.
2. **Resolve remote and default branch** through the ladder in
   `docs/git-remote-resolution.md`, transcribed into Python. The layer order is pinned by
   a test, and layer 3 (`gh repo view`) is optional — `gh` absent, unauthenticated, or
   erroring falls through to layer 4. Unresolvable default → silent.
3. **Fetch once**: `git fetch --quiet <remote> <default>`, subprocess timeout 8s. Failure,
   offline, or timeout is not fatal — carry on with whatever remote-tracking ref already
   exists. A stale ref can only under-report a merge, never invent one. No
   `refs/remotes/<remote>/<default>` at all → silent.
4. **Decide merged**: `git merge-base --is-ancestor HEAD <remote>/<default>`, exit 0 ⇒
   merged.
5. **Behind count**: `git rev-list --count <default>..<remote>/<default>`. Skipped when the
   local default branch does not exist.
6. **Stale locals**: `git for-each-ref refs/heads`, minus the default branch, keeping those
   that are ancestors of `<remote>/<default>` — one `merge-base --is-ancestor` per branch.

### What it emits

Through `hookSpecificOutput.additionalContext`, at most three lines:

```
Branch feat/release-skill has been merged into main.
Local main is 3 commits behind origin/main.
Merged branches still present locally: feat/release-skill, feat/ship-fix.
```

Line 1 fires only when HEAD is a non-default branch that is merged. Line 3 is the deletion
list and is independent of HEAD — it catches the common case where you already switched
back to the default branch and the merged branches are quietly accumulating. The hook
itself never deletes, checks out, or pulls anything; it reports, and the agent offers.

One case beyond the issue's wording: when HEAD **is** the default branch and it is behind,
emit only the behind line. That is the same "go pull" prompt from the same data at no extra
cost. On the default branch and current → silent.

### Failure contract

`main()` is wrapped so any unexpected exception exits 0 with no output. A hook that errors
at session start is worse than a hook that says nothing.

## Tests

Pytest, against temp repos built from a bare origin plus a clone:

- non-repo cwd → silent
- repo with no remote → silent
- detached HEAD → silent
- unmerged branch → silent
- merged branch checked out → all three lines, with itself in the deletion list
- on the default branch, current, but a merged local branch lingers → deletion line only
- on the default branch and behind, nothing lingering → behind line only
- on the default branch, current, nothing lingering → silent
- unreachable remote → silent, no traceback, exit 0
- `git init`-style repo with no `refs/remotes/<remote>/HEAD` → default still resolves via a
  later layer
- structural: `hooks/hooks.json` parses, uses `${CLAUDE_PLUGIN_ROOT}`, and names a file that
  exists — mirroring `tests/test_hook_wiring.py` and `tests/test_hook_path_portability.py`

## Scope

Not part of #93. `/release` already self-detects: it fetches and refuses if the default
branch is not current, so it never depends on being told. This is the general-session case.

`docs/git-remote-resolution.md` gains the hook in its consumer list, noting that a Python
transcription of the ladder lives in `hooks/merged_branch.py`.
