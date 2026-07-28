---
name: config-sync-setup
description: >
  This skill should be used when the user wants to set up config sync for the first
  time, connect a new machine to an existing sync repo, or re-initialise after a
  broken setup. Trigger phrases include: "set up config sync", "sync my Claude setup
  to a new machine", "connect this machine", "join my config-sync repo",
  "/config-sync-setup".
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash, Read, Write, AskUserQuestion
metadata:
  version: "0.4.0"
---

# config-sync-setup

Set up **Claude config sync** on this machine — keeps your `~/.claude` config files
(CLAUDE.md, `rules/`, `skills/`, `agents/`, the `memory/` files, `settings.json`) in
sync across machines via a private Git repo. Handles both cases automatically:
- **First time ever**: create a new Git repo and push the initial snapshot
- **Joining existing repo**: clone the remote, then run `/config-sync` to merge

> **Not the knowledge brain.** This syncs your Claude *config files* across machines.
> It is **not** the fact-recall system — for capturing/recalling knowledge use
> **Mente Apex memory** (the `mem` CLI / the `mente-apex-memory` MCP server). Different system.

## Step 1 — Migrate legacy paths, then check state

```bash
ENGINE="${CLAUDE_PLUGIN_ROOT:-}/scripts/config_sync.py"
if [ ! -f "$ENGINE" ]; then
  # CLAUDE_PLUGIN_ROOT is unset outside plugin context (e.g. a standalone-copied
  # skill) — fall back to the newest engine in the installed plugin cache.
  # sort -V version-sorts the cached versions; tail -1 takes the highest, so an
  # older cached version can never shadow the current one.
  ENGINE=$(ls -d "$HOME/.claude/plugins/cache/"*/mente-apex/*/scripts/config_sync.py \
    2>/dev/null | sort -V | tail -1)
fi
[ -f "$ENGINE" ] || { echo "config_sync.py engine not found — run: claude plugin install mente-apex"; exit 1; }

# Never the interpreter the OS ships: it is 3.9 on stock macOS, and every
# module this plugin ships is formatted at py314, which emits syntax older
# interpreters reject outright. Which interpreter uv picks is the operator's
# call, not this file's: a repo's own .python-version wins, then the global pin.
# A function, not a variable — zsh does not word-split an unquoted expansion,
# so a multi-word PY="..." would be looked up as one long command name.
py() { uv run --no-project python "$@"; }

# With no pin anywhere, uv picks whatever it can find, and "whatever it can
# find" differs per machine — the drift this plugin exists to prevent. uv walks
# up from $PWD for a .python-version before falling back to the global pin, so
# this looks in the same order rather than only at the current directory.
pinned() {
  d=$PWD
  while [ "$d" != "/" ]; do
    [ -f "$d/.python-version" ] && return 0
    d=$(dirname "$d")
  done
  [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/uv/.python-version" ]
}
if ! pinned; then
  echo "No Python pin found — uv is choosing an interpreter for you. Pin one:"
  echo "  uv python pin --global $(py -c 'import sys; print(sys.version.split()[0])')"
fi
CONFIG="$HOME/.claude/config-sync-config.json"

# One-time, idempotent rename of any legacy open-memory-* paths. No-op otherwise.
py "$ENGINE" migrate

py "$ENGINE" machine-id
py "$ENGINE" status
```

If `~/.claude/config-sync-config.json` already exists, tell the user their current
setup and ask if they want to re-initialise or join a different remote. Offer to
run `/config-sync` instead if everything looks healthy.

## Step 2 — Check dependencies

```bash
command -v git >/dev/null 2>&1 && echo "git: ok" || echo "git: MISSING — install git first"
command -v uv >/dev/null 2>&1 && echo "uv: ok" || echo "uv: MISSING — install uv first (https://docs.astral.sh/uv/)"
```

If anything is missing, stop and tell the user what to install.

## Step 3 — Security notice + get the remote URL

Before asking for the remote, inform the user exactly what will be synced:

> **What config sync exports to Git:**
> - `CLAUDE.md`, `rules/`, `skills/`, `agents/` — your instructions and workflows
> - `memory/` — the memory files accumulated under `~/.claude/memory/`
> - `settings.json` — hooks, permissions, MCP server command/args (**env vars with API keys are stripped**)
> - `keybindings.json`
>
> **What is NEVER exported:**
> OAuth tokens · API keys in env vars · `~/.claude.json` · session transcripts · any key/value whose name matches `api_key`, `token`, `secret`, `password`, or `credential`
>
> The `memory/` files may contain information from your conversations. Review `~/.claude/memory/` if you have concerns before proceeding.

> **Hook paths are made portable automatically.** Machine-absolute paths inside
> `settings.json` hook `command` strings are rewritten to `${HOME}`-relative sentinels
> on export and expanded back to this machine's real paths on import, so a synced hook
> works even when `$HOME` differs. If a repo lives at a *different* sub-`$HOME` location
> on another machine (e.g. `~/Projects/…` here vs `~/dev/…` there), declare it per-machine
> with an env var `CONFIG_SYNC_ROOT_<NAME>=<absolute path>` (machine-local, never synced);
> its hook paths then travel as `${<NAME>}` and resolve correctly on each machine.

> **Provisioning hooks.** A repo that ships hooks can declare them in a
> `hooks/hooks.json` (the same format Claude Code plugins use). On this machine,
> run `/config-sync` and accept the *wire-hooks* step to register any declared
> hooks that aren't in `settings.json` yet — no hand-editing. Declare where each
> such repo lives with `CONFIG_SYNC_ROOT_<NAME>` so its `${CLAUDE_PLUGIN_ROOT}`
> hook paths resolve on every machine.

Then ask the user for their Git remote URL (e.g. `git@github.com:you/claude-config.git`).

Security check: a URL can't reliably reveal whether the repo is private, so **always**
warn — never gate this on the URL "looking" public:
> "⚠ This repo will hold your CLAUDE.md, memory, rules, and skills. Make **sure** it is
> private before continuing — a public repo would expose all of it. Confirm it's private?"

Ask for confirmation before proceeding.

## Step 3b — Scan for secrets before export

Before exporting any local state to the repo, scan for secrets that shouldn't be
committed. This is the same secret-scan gate `/config-sync` runs before every push
— `scan --gate` prints any findings and exits non-zero when the config isn't clean:

```bash
if py "$ENGINE" scan --gate; then
  SCAN_CLEAN=1
else
  SCAN_CLEAN=0
fi
```

If `SCAN_CLEAN` is `0`, the findings were printed above — use **AskUserQuestion**
to ask whether to continue anyway. If the user declines, stop here.

## Step 4 — Detect: new repo or joining?

```bash
# Try fetching the remote — if it succeeds and has content, we're joining
git ls-remote "$REMOTE_URL" HEAD 2>/dev/null && echo "remote-exists" || echo "remote-empty"
```

**If remote is empty → new repo:**

```bash
REPO="$HOME/.claude/config-sync-repo"
mkdir -p "$REPO/machines" "$REPO/consolidated" "$REPO/meta"
cd "$REPO"
git init
git remote add origin "$REMOTE_URL"

# Export current local state
MACHINE_ID=$(py "$ENGINE" machine-id)
py "$ENGINE" export > "$REPO/machines/$MACHINE_ID.json"
cp "$REPO/machines/$MACHINE_ID.json" "$REPO/consolidated/snapshot.json"

echo '{"syncs":[]}' > "$REPO/meta/sync-log.json"

git add .
git commit -m "init: $(py "$ENGINE" machine-id) on $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git branch -M main
git push -u origin main
```

**If remote has content → joining:**

```bash
REPO="$HOME/.claude/config-sync-repo"

# Back up current state before touching anything
BACKUP="$HOME/.claude/config-sync-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
py "$ENGINE" export > "$BACKUP/pre-join-snapshot.json"
echo "Backup saved to $BACKUP"

# Clone the remote (or pull if the dir already exists from a prior attempt)
if [ -d "$REPO/.git" ]; then
  git -C "$REPO" pull origin main
else
  git clone "$REMOTE_URL" "$REPO"
fi

MACHINE_ID=$(py "$ENGINE" machine-id)
py "$ENGINE" export > "$REPO/machines/$MACHINE_ID.json"
```

Ask the user how to handle existing local content:
- **Merge (recommended)** — combine local + network using the smart merge
- **Keep mine** — push local snapshot, keep local files as-is
- **Take theirs** — replace local state with the consolidated network snapshot

For **"Merge"**, don't re-implement the merge here — register this machine (Step 5)
and then run the canonical sync cycle, which merges the local snapshot, the
consolidated snapshot, and every other machine's snapshot in one pass:

```bash
# Just register + push this machine (Step 5), then:
echo "Setup complete — run /config-sync now to merge and apply the network."
```

For **"Keep mine"**: push the local snapshot without importing remote content:
```bash
# Local files stay unchanged — just register this machine in the repo.
# The local snapshot was already exported above; nothing else to import.
echo "Keeping local state — will push this machine's snapshot to the repo."
```

For **"Take theirs"**:
```bash
py "$ENGINE" import "$REPO/consolidated/snapshot.json"
```

## Step 5 — Register this machine and push

```bash
cd "$REPO"
git add machines/
git commit -m "join: $MACHINE_ID on $(date -u +%Y-%m-%dT%H:%M:%SZ)" 2>/dev/null || echo "nothing to commit"
git push origin main
```

Save config:
```bash
py - <<EOF
import json, os
from pathlib import Path
cfg = {
    "remote": "$REMOTE_URL",
    "machine_id": "$(py "$ENGINE" machine-id)",
    "last_sync": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
Path(os.path.expanduser("~/.claude/config-sync-config.json")).write_text(json.dumps(cfg, indent=2))
print("Config saved.")
EOF
```

## Step 5b — Log the setup event

```bash
py "$ENGINE" log-sync "$HOME/.claude/config-sync-repo" "setup" "machine joined repo"
```

## Step 6 — Confirm

Tell the user:
- Their machine ID
- The remote URL
- The current local inventory (output from `py "$ENGINE" status`)
- If they chose **Merge** on join: "Run `/config-sync` now to merge and apply the network."
- Next step: "Run `/config-sync` any time you want to sync. Run `/config-sync status`
  to see the machines in your network, shared artifacts, and recent sync history."
