# Resolving the remote and the default branch

Shared by every skill in this plugin that pushes, targets a base branch, or checks
whether the working branch is current — today `/ship` (Step 1) and `/release` (Step 1).

This lives in one file for a specific reason. The resolution is fifteen lines of
non-obvious shell, and the failure it guards against is silent: `refs/remotes/<remote>/HEAD`
is set only by a fresh `git clone`. Any repo created with `git init` + `git remote add`
has no such ref, so `git symbolic-ref` alone returns nothing and a skill that trusts it
targets the wrong base branch. Restating this per skill is how the copies drift.

## Run it in the same shell as its consumers

`REMOTE` and `DEFAULT` are shell variables, and every tool call starts a **fresh shell**.
They do not survive from one Bash call to the next. Run the two blocks below and the
commands that read their values in **one invocation**, or re-run the resolution at the top
of each later block that needs them.

Getting this wrong fails silently in the worst way: `git fetch "$REMOTE" "$DEFAULT"` in a
second call becomes `git fetch "" ""`, and the calling skill carries on believing it
fetched. Guarding uses with `[ -n "$REMOTE" ] && [ -n "$DEFAULT" ]` turns that silence
into something visible; it does not remove the need to keep the resolution in the same
shell.

## Resolve the remote

Prefer `origin`; otherwise take the first configured remote. Never hardcode `origin` —
forks and upstream-tracking repos name theirs differently.

```bash
REMOTE=$(git remote | grep -qx origin && echo origin || git remote | head -1)
echo "=== remote ===" ; echo "${REMOTE:-(none)}"
```

An empty result means there is no remote at all. The calling skill decides what that
means for it: `/ship` can still branch and commit; `/release` cannot publish and must
refuse.

## Resolve the default branch

Four layers, cheapest first. Each runs only if the previous produced nothing.

```bash
DEFAULT=""
if [ -n "$REMOTE" ]; then
  # 1. Local ref — instant, but only exists on a freshly cloned repo.
  DEFAULT=$(git symbolic-ref "refs/remotes/$REMOTE/HEAD" 2>/dev/null | sed 's@.*/@@')
  # 2. Ask the remote directly — a network round-trip, always authoritative.
  [ -z "$DEFAULT" ] && DEFAULT=$(git remote show "$REMOTE" 2>/dev/null | sed -n 's/.*HEAD branch: //p')
  # 3. Ask GitHub — works when the remote is unreachable but gh is authenticated.
  [ -z "$DEFAULT" ] && DEFAULT=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null)
fi
# 4. Guess from local branches, last resort.
for candidate in main master; do
  [ -z "$DEFAULT" ] && git show-ref --verify --quiet "refs/heads/$candidate" && DEFAULT="$candidate"
done
echo "=== default ===" ; echo "${DEFAULT:-(unknown — confirm with the user)}"
```

`(unknown)` means detection found no signal at all. **Never guess past this point** — ask
the user which branch to target. A wrong default branch silently opens a PR against the
wrong base, or pushes a release to the wrong line of development.

## Optional: set the local ref once

A user hitting layer 2 or 3 repeatedly can make layer 1 succeed from then on:

```bash
git remote set-head <remote> --auto
```

Suggest it; never run it unasked. It writes to their repo config.
