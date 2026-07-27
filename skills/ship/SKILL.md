---
name: ship
description: >
  Use whenever the user wants their current uncommitted (or already-committed) work
  turned into a GitHub pull request — the commit → push → open-PR handoff. This skill
  OWNS that pipeline: invoke it the moment the user signals a change is finished and
  should go up, whether they say "ship it," "ship this," "ship my changes," "/ship,"
  "this is good to go," "looks done," "I'm happy with this fix — push it up," or name
  the steps directly ("commit and pr," "commit this and open a PR," "push it up and put
  up a PR," "branch, commit and pr"). Also use to re-open or re-create a PR for work
  already committed. Trigger even when only part of the chain is mentioned, and even
  when phrased as wanting review ("get it reviewed," "put up a PR so I can review it") —
  prefer this over generic finish-the-branch or request-code-review helpers.
  Do NOT use for merging or closing a PR, reviewing/commenting on someone's PR,
  rebasing/squashing/force-pushing history, syncing config across machines, or emailing
  files.
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash, Read, AskUserQuestion
metadata:
  version: "0.7.0"
---

# ship

Turn the current working changes into a pushed branch and an open pull request, in one
pass. This is the workflow the user runs constantly ("branch, commit and pr before
continuing") — the point of the skill is to make it one fast, predictable motion instead
of re-typing the same five git commands every time.

The flow: **inspect state → make a branch if needed → stage → draft commit + PR → show the
plan → commit, push, and open the PR.** Launching this skill *is* the go-ahead — the user
asked to ship, so don't stop for a redundant yes/no. Show the plan as a transparent
announcement of what's about to happen, then execute in the same pass so the user isn't
babysitting it. The only things that still halt the flow are genuine **blockers** (no
remote, or the base branch can't be determined) and a narrow **safety** stop (an untracked
file that looks like a secret about to be pushed public) — never a bare "are you sure?".

## Conventions this skill follows

These come from the user's standing preferences and the repos they work in — keep them
consistent so shipped history stays clean:

- **Conventional Commits** for the subject line: `type(scope): summary` (e.g.
  `feat(ship): add /ship workflow skill`, `fix(sync): handle long vector ids`). Common
  types: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`. Derive the scope from the
  area touched; omit it if nothing fits.
- **Never commit directly to the default branch.** If the current branch is `main` or
  `master`, create a feature branch first. This mirrors the harness rule and keeps the
  default branch clean.
- **Commit message footer** — every commit ends with the co-author trailer the harness
  prescribes for the *active* model this session (Claude Code injects the exact model
  name). Use that trailer verbatim; if none is configured, fall back to a model-neutral
  `Co-Authored-By: Claude <noreply@anthropic.com>`. Never hardcode a specific model name.
- **PR body footer** — every PR body ends with:
  ```
  🤖 Generated with [Claude Code](https://claude.com/claude-code)
  ```
- **PRs open ready for review** (not draft) unless the user asks otherwise.

## Step 1 — Inspect the repo state

Gather everything needed to plan the ship in one shot. Run from the repo the user is
working in (the current working directory unless they point elsewhere):

```bash
git rev-parse --is-inside-work-tree 2>/dev/null || { echo "NOT_A_GIT_REPO"; exit 0; }
```

Resolve the remote and the base branch using the shared procedure in
[docs/git-remote-resolution.md](../../docs/git-remote-resolution.md) — run that file's two
blocks to set `REMOTE` and `DEFAULT`, then continue with the rest of this block. Both
values are used throughout the steps below; never reintroduce a literal `origin`.

```bash
# REMOTE and DEFAULT are now set — see docs/git-remote-resolution.md.

# Current branch. EMPTY output means detached HEAD — Step 2 must create a branch.
BRANCH=$(git branch --show-current)
echo "=== branch ==="   ; echo "${BRANCH:-(detached HEAD)}"

# Are we in a LINKED worktree (not the main checkout)? A linked worktree's git-dir is
# .git/worktrees/<name>; the main checkout's git-dir equals the shared common-dir. In a
# worktree, Step 2 keeps branch handling minimal — no fetch/sync/rescue, no touching the
# shared <default> ref — because a worktree is a deliberate, isolated checkout.
[ "$(git rev-parse --git-dir)" != "$(git rev-parse --git-common-dir)" ] \
  && WORKTREE=yes || WORKTREE=no
echo "=== worktree ===" ; echo "$WORKTREE"

echo "=== status ==="   ; git status --short
echo "=== staged ==="   ; git diff --cached --stat
echo "=== unstaged ==="  ; git diff --stat
# Exactly what `git add -A` would newly stage — surface it so nothing sneaks in.
echo "=== untracked ==="; git ls-files --others --exclude-standard
if [ -n "$REMOTE" ] && [ -n "$DEFAULT" ]; then
  echo "=== ahead/behind vs $REMOTE/$DEFAULT ==="
  git rev-list --left-right --count "$REMOTE/$DEFAULT"...HEAD 2>/dev/null || echo "(no upstream yet)"
fi
```

Read the output and decide:

- **Not a git repo** → tell the user, offer to `git init`, and stop. Don't invent a repo.
- **No remote** (`remote` is `(none)`) → you can still branch + commit, but push/PR need a
  remote. Note it and ask whether to add one or stop after the commit.
- **Default branch `(unknown)`** → detection found no signal. Don't guess a base for the
  PR; ask the user which branch to target before doing anything outward.
- **Untracked files present** → these are what `git add -A` will sweep in. List them on
  the plan's `Adds` line so they're visible. Only *halt* if one looks like a secret (see
  Step 4's safety stop); build output or scratch files are just noted, not gated.
- **Nothing to commit and nothing unpushed** → there's nothing to ship; say so and stop.
- **Nothing to commit but there are unpushed commits / an existing PR** → skip staging
  and the commit; go straight to push + PR (see "Existing PR" below). This covers
  "re-create the PR" / "open a pr for what I already committed".

## Step 2 — Decide the branch

- **In a linked worktree** (`worktree` printed `yes`) → keep branch handling **minimal**;
  never fetch/sync or rewind the shared `<default>` ref, because a worktree is a
  deliberate, isolated checkout.
  - On a **feature branch** → use it as-is (don't create another branch).
  - On the **default branch, or detached HEAD** → committing here isn't allowed, so create
    a feature branch off the **current commit** — a plain `git checkout -b`, *no* fetch,
    *no* sync, *no* reset of `<default>`. Don't stop to ask; just branch and continue.
  Show the derived name in the plan first, as always, so the user can override it.
- **Already on a feature branch** (not the default branch, main checkout) → use it as-is.
  Do not create another branch.
- **On the default branch, or in detached HEAD** (`branch` printed `(detached HEAD)`) →
  a feature branch must be created before committing. Derive its name from the change and
  the Conventional Commit type: `<type>/<short-kebab-summary>` (e.g. `feat/ship-skill`,
  `fix/long-vector-ids`). Keep it short and descriptive. Don't create it yet — show it in
  the plan first so the user can override the name.
  - **When on the default branch, sync it first** so the new branch starts from an
    up-to-date base instead of a stale local `<default>`: fetch the remote, then branch
    off the *fetched* tip. The exact commands (and the committed-vs-uncommitted split that
    keeps this from dropping any local commits) are in Step 5.
  - **Detached HEAD** just branches off the current commit — there's nothing to sync.
    (`git checkout -b` branches at the current commit either way.)
- **Whenever you create a branch, make sure the name is free** before showing it in the
  plan (`git show-ref --verify --quiet refs/heads/<name>` succeeds if it's taken). Clashes
  are common in multi-worktree repos where sibling branches accumulate. If it's taken,
  disambiguate (`<name>-2`, `<name>-3`, …) and use the free name. Step 5 re-checks this
  defensively at creation time, so the ship never dies on a "branch already exists" error.

## Step 3 — Draft the commit and PR

Look at the actual diff so the message reflects what changed — don't guess from filenames
alone:

```bash
git diff --cached 2>/dev/null; git diff 2>/dev/null   # whichever has content
```

- **Commit subject**: one Conventional Commit line. If the change spans several unrelated
  things, prefer the dominant one for the subject and mention the rest in the body rather
  than inventing a fake umbrella scope.
- **Commit body** (optional): a short bullet or two only if the change isn't
  self-explanatory from the subject. Plus the `Co-Authored-By` trailer.
- **PR title**: a clean human sentence (not necessarily the Conventional Commit line) —
  e.g. "Add /ship workflow skill".
- **PR body**: a couple of sentences on what and why, a short bullet list if it helps a
  reviewer, then the Claude Code footer.

## Step 4 — Show the plan, then execute

Present the compact plan as an announcement of what's about to happen, then go straight to
Step 5 in the same pass. Do **not** stop for a yes/no — launching the skill was the
consent.

```
Ship plan
  Repo    : <repo name>  (cwd: <path>)
  Remote  : <remote name>
  Branch  : <branch>   [new, off <default> synced from <remote>] | [existing] | [worktree: as-is | new off current, no sync] | [new, off detached HEAD]
  Files   : <N changed>  (+<add>/-<del>)
  Adds    : <untracked paths git add -A will stage, or "none">
  Commit  : <conventional commit subject>
  PR      : "<pr title>"   → base: <default branch>, ready for review
```

List the untracked paths explicitly on the `Adds` line (not just a count) so the user can
see exactly what's being committed. If there are none, say "none".

Halt and ask (via **AskUserQuestion**) **only** for a genuine blocker or safety issue —
never to re-confirm the ship itself:

- **No remote** → branch + commit is possible, but push/PR can't proceed. Ask whether to
  add a remote or stop after the commit.
- **Base branch `(unknown)`** → there's no safe base to open the PR against. Ask which
  branch to target.
- **A staged/untracked path looks like a secret** (e.g. `.env`, `*.pem`, `id_rsa`,
  `credentials*`) → flag it and ask before it's pushed public, since that's hard to undo.

Absent one of those, don't ask anything — show the plan and ship. The user can always
interrupt if they want to change the branch name, commit subject, or PR title mid-flight.

## Step 5 — Execute

Run in order. Stop and report if any step fails — don't paper over a failed push.
Substitute the **resolved** `<remote>` and `<default branch>` from Step 1 — do not
reintroduce a literal `origin`.

**Steps 2–3 (stage + commit) run only when there is something to commit.** On the
"already committed, just push + PR" path (Step 1 found no working-tree changes), skip
straight to step 4 — never `git add -A` + `git commit` with nothing staged (that either
errors or, worse, invites an empty commit).

```bash
# 1. Branch. First resolve a collision-free name, then pick the one case for Step 1's state.
#
# Collision guard: the derived name may already exist — common in multi-worktree repos
# where sibling branches pile up — and `git checkout -b` fails on a clash. Take the first
# free name (<branch>, <branch>-2, <branch>-3, …). show-ref also sees branches checked out
# in other worktrees, so this won't collide with those either. Use $BRANCH everywhere below.
BRANCH="<branch>"; branch_base="$BRANCH"; next_suffix=2
while git show-ref --verify --quiet "refs/heads/$BRANCH"; do
  BRANCH="$branch_base-$next_suffix"; next_suffix=$((next_suffix + 1))
done
[ "$BRANCH" != "$branch_base" ] && echo "Branch '$branch_base' already exists — shipping as '$BRANCH'."
#
#  (0) In a linked worktree (WORKTREE=yes) → minimal handling, never sync/rewind <default>:
#        - on a feature branch → SKIP the rest of this block (used as-is)
#        - on <default> or detached → branch off the CURRENT commit, no fetch/sync:
#            git checkout -b "$BRANCH"
#      Then continue to step 2 (stage). Do NOT run case (c)'s sync/rescue in a worktree.
#
#  (a) Already on a feature branch (main checkout) → SKIP the rest of this block; used as-is.
#
#  (b) Detached HEAD, or no remote to sync against → branch off the current commit:
#        git checkout -b "$BRANCH"
#
#  (c) On the default branch WITH a remote → sync <default>, then branch off the right
#      base. Never drop local commits: branch off the fetched tip only when nothing was
#      committed to local <default>; otherwise rescue the commits onto the branch first.
git fetch "<remote>" "<default>" 2>&1 || echo "fetch failed — will branch off local <default> (not synced)"

# How many commits local <default> is ahead of the remote (0 ⇒ work is uncommitted/none).
AHEAD=$(git rev-list --count "<remote>/<default>..HEAD" 2>/dev/null || echo 0)

if [ "$AHEAD" -gt 0 ]; then
  # Committed to local <default>: keep those commits by branching off the current HEAD,
  # then move local <default> back to the synced remote (commits live on the branch now).
  git checkout -b "$BRANCH"
  git branch -f "<default>" "<remote>/<default>"
  echo "Moved $AHEAD commit(s) off <default> onto $BRANCH; reset local <default> to <remote>/<default>."
else
  # Uncommitted (or clean): branch off the freshly-fetched tip, carrying working-tree
  # changes. If local edits overlap incoming <default> changes, git aborts — fall back to
  # branching off local <default> and tell the user it couldn't be advanced.
  git checkout -b "$BRANCH" "<remote>/<default>" 2>/dev/null \
    || { echo "Local edits overlap incoming <default> — branching off local <default> instead."; git checkout -b "$BRANCH"; }
fi

# 2. Stage the work (SKIP on the push-only path).
git add -A                            # only the intended paths if the user vetoed some

# 3. Commit (SKIP on the push-only path). Heredoc keeps the trailer intact.
# Replace the trailer below with the active model's trailer prescribed by the
# harness this session; use the neutral form only if none is configured.
git commit -F - <<'MSG'
<conventional commit subject>

<optional body>

Co-Authored-By: Claude <noreply@anthropic.com>
MSG

# 4. Push and set upstream (resolved remote — not a hardcoded 'origin'; $BRANCH may have
#    been disambiguated above, so use it rather than the originally-planned name).
git push -u "<remote>" "$BRANCH"

# 5. Open the PR (ready for review).
gh pr create --base "<default branch>" --head "$BRANCH" \
  --title "<pr title>" --body "$(cat <<'BODY'
<pr body>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
)"
```

### Existing PR

If a PR already exists for this branch (`gh pr view` succeeds), don't create a duplicate —
push the new commits (step 4) and tell the user the existing PR now includes them, with
its URL. Only "re-create" a PR if the user explicitly asks (e.g. the old one was closed):
in that case `gh pr create` again.

### If `gh` is unavailable or unauthenticated

`gh` may be missing or not logged in. Detect it (`gh auth status`), and if so: finish the
push, then give the user the compare URL to open the PR manually
(`https://github.com/<owner>/<repo>/compare/<default>...<branch>`), and suggest they run
`gh auth login` (via `! gh auth login` in their session) to enable one-step PRs next time.

## Step 6 — Report

Give a tight summary with the links that matter:

```
✓ Shipped
  Branch : <branch>  (pushed)  [off <default> synced from <remote>]
  Commit : <sha>  <subject>
  PR     : <url>   (ready for review)
```

If the work had been on `<default>`, note how the base was prepared — e.g. "branched off
freshly-fetched `<remote>/<default>`", or "rescued N commit(s) off `<default>` and reset
local `<default>` to `<remote>/<default>`" — so the user knows what happened to `main`.

If you stopped early (no remote, gh unauthenticated, nothing to ship), say exactly where
it stopped and what the user needs to do to finish.

## Scope — what /ship does not do

Keep this focused so it stays fast and predictable:

- It does **not** run tests, linters, or CI fixes. If the user wants checks before
  shipping, that's a separate concern — run them first, then `/ship`.
- It does **not** merge the PR. Shipping opens the PR; merging is a deliberate later step.
- It does **not** rebase, squash existing history, or force-push. If the user needs that,
  do it explicitly outside this flow.
