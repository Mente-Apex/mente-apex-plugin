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
  version: "0.1.0"
---

# ship

Turn the current working changes into a pushed branch and an open pull request, in one
pass. This is the workflow the user runs constantly ("branch, commit and pr before
continuing") — the point of the skill is to make it one fast, predictable motion instead
of re-typing the same five git commands every time.

The flow: **inspect state → make a branch if needed → stage → draft commit + PR → show a
plan → on one "go", commit, push, and open the PR.** There is exactly one confirmation
checkpoint, right before anything leaves the machine, because pushing and opening a PR
are outward-facing and effectively public — but everything up to that point is automatic
so the user isn't babysitting it.

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
- **Commit message footer** — every commit ends with the user's required trailer:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```
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
echo "=== branch ==="    ; git branch --show-current
echo "=== default ==="   ; git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@.*/@@' || echo "(no origin HEAD)"
echo "=== remote ==="    ; git remote -v | head -1
echo "=== status ==="    ; git status --short
echo "=== staged ==="    ; git diff --cached --stat
echo "=== unstaged ==="  ; git diff --stat
echo "=== ahead/behind ==="; git rev-list --left-right --count origin/HEAD...HEAD 2>/dev/null || echo "(no upstream)"
```

Read the output and decide:

- **Not a git repo** → tell the user, offer to `git init`, and stop. Don't invent a repo.
- **No remote** → you can still branch + commit, but push/PR need a remote. Note it and
  ask whether to add one or stop after the commit.
- **Nothing to commit and nothing unpushed** → there's nothing to ship; say so and stop.
- **Nothing to commit but there are unpushed commits / an existing PR** → skip staging
  and the commit; go straight to push + PR (see "Existing PR" below). This covers
  "re-create the PR" / "open a pr for what I already committed".

## Step 2 — Decide the branch

- **Already on a feature branch** → use it as-is. Do not create another branch.
- **On the default branch (`main`/`master`)** → derive a feature branch name from the
  change and the Conventional Commit type: `<type>/<short-kebab-summary>` (e.g.
  `feat/ship-skill`, `fix/long-vector-ids`). Keep it short and descriptive. Don't create
  it yet — show it in the plan first so the user can override the name.

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

## Step 4 — Show the plan and get one confirmation

Present a compact plan and stop for a single yes/no. This is the one checkpoint:

```
Ship plan
  Repo    : <repo name>  (cwd: <path>)
  Branch  : <branch>   [new, off <default>] | [existing]
  Files   : <N changed>  (+<add>/-<del>)
  Commit  : <conventional commit subject>
  PR      : "<pr title>"   → base: <default branch>, ready for review

Proceed? (yes / edit / no)
```

- **yes** → run Step 5.
- **edit** → let the user adjust the branch name, commit subject, or PR title/body, then
  re-show the plan.
- **no** → stop; change nothing outward. (Any branch already created locally is harmless.)

Use AskUserQuestion only if you genuinely need a decision (e.g. no remote, or the diff is
empty but they asked to ship). Otherwise a plain plan + confirmation is enough.

## Step 5 — Execute

Run in order. Stop and report if any step fails — don't paper over a failed push.

```bash
# 1. Branch (only if on the default branch)
git checkout -b "<branch>"            # skip if already on a feature branch

# 2. Stage everything the user is working on
git add -A

# 3. Commit (heredoc keeps the trailer intact)
git commit -F - <<'MSG'
<conventional commit subject>

<optional body>

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG

# 4. Push and set upstream
git push -u origin "<branch>"

# 5. Open the PR (ready for review)
gh pr create --base "<default branch>" --head "<branch>" \
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
  Branch : <branch>  (pushed)
  Commit : <sha>  <subject>
  PR     : <url>   (ready for review)
```

If you stopped early (no remote, gh unauthenticated, nothing to ship), say exactly where
it stopped and what the user needs to do to finish.

## Scope — what /ship does not do

Keep this focused so it stays fast and predictable:

- It does **not** run tests, linters, or CI fixes. If the user wants checks before
  shipping, that's a separate concern — run them first, then `/ship`.
- It does **not** merge the PR. Shipping opens the PR; merging is a deliberate later step.
- It does **not** rebase, squash existing history, or force-push. If the user needs that,
  do it explicitly outside this flow.
