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
  version: "0.2.0"
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
ENGINE="${CLAUDE_PLUGIN_ROOT}/scripts/config_sync.py"
CONFIG="$HOME/.claude/config-sync-config.json"

# One-time, idempotent rename of any legacy open-memory-* paths. No-op otherwise.
python3 "$ENGINE" migrate

python3 "$ENGINE" machine-id
python3 "$ENGINE" status
```

If `~/.claude/config-sync-config.json` already exists, tell the user their current
setup and ask if they want to re-initialise or join a different remote. Offer to
run `/config-sync` instead if everything looks healthy.

## Step 2 — Check dependencies

```bash
command -v git >/dev/null 2>&1 && echo "git: ok" || echo "git: MISSING — install git first"
command -v python3 >/dev/null 2>&1 && echo "python3: ok" || echo "python3: MISSING"
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

Then ask the user for their Git remote URL (e.g. `git@github.com:you/claude-config.git`).

Security check: if the URL looks like a public GitHub repo (no `.git` private indicator
or matches common public patterns), warn them:
> "⚠ This looks like it could be a public repository. Your CLAUDE.md, memory, rules,
> and skills will be stored there. Please make sure the repo is private before continuing."

Ask for confirmation before proceeding.

## Step 3b — Scan for secrets before export

Before exporting any local state to the repo, scan for secrets that shouldn't be
committed. This is the same secret-scan gate `/config-sync` runs before every push:

```bash
SCAN_RESULT=$(python3 "$ENGINE" scan)
WARNINGS=$(echo "$SCAN_RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['warnings']))")

if [ "$WARNINGS" -gt 0 ]; then
  echo "⚠ Secret scan found $WARNINGS potential issue(s) in your config files:"
  echo "$SCAN_RESULT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for w in d['warnings']:
    print(f\"  {w['file']}:{w['line']} — {w['preview']}\")
"
  echo ""
  echo "Review the files above before pushing. Continue anyway? (yes/no)"
  # If user says no, stop here. If yes, proceed.
fi
```

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
MACHINE_ID=$(python3 "$ENGINE" machine-id)
python3 "$ENGINE" export > "$REPO/machines/$MACHINE_ID.json"
cp "$REPO/machines/$MACHINE_ID.json" "$REPO/consolidated/snapshot.json"

echo '{"syncs":[]}' > "$REPO/meta/sync-log.json"

git add .
git commit -m "init: $(python3 "$ENGINE" machine-id) on $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git branch -M main
git push -u origin main
```

**If remote has content → joining:**

```bash
REPO="$HOME/.claude/config-sync-repo"

# Back up current state before touching anything
BACKUP="$HOME/.claude/config-sync-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
python3 "$ENGINE" export > "$BACKUP/pre-join-snapshot.json"
echo "Backup saved to $BACKUP"

# Clone the remote (or pull if the dir already exists from a prior attempt)
if [ -d "$REPO/.git" ]; then
  git -C "$REPO" pull origin main
else
  git clone "$REMOTE_URL" "$REPO"
fi

MACHINE_ID=$(python3 "$ENGINE" machine-id)
python3 "$ENGINE" export > "$REPO/machines/$MACHINE_ID.json"
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
python3 "$ENGINE" import "$REPO/consolidated/snapshot.json"
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
python3 - <<EOF
import json, os
from pathlib import Path
cfg = {
    "remote": "$REMOTE_URL",
    "machine_id": "$(python3 "$ENGINE" machine-id)",
    "last_sync": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
Path(os.path.expanduser("~/.claude/config-sync-config.json")).write_text(json.dumps(cfg, indent=2))
print("Config saved.")
EOF
```

## Step 5b — Log the setup event

```bash
python3 "$ENGINE" log-sync "$HOME/.claude/config-sync-repo" "setup" "machine joined repo"
```

## Step 6 — Confirm

Tell the user:
- Their machine ID
- The remote URL
- The current local inventory (output from `python3 "$ENGINE" status`)
- If they chose **Merge** on join: "Run `/config-sync` now to merge and apply the network."
- Next step: "Run `/config-sync` any time you want to sync. Run `/config-sync-manage`
  to check repo status, promote notes into rules, or share skills."
