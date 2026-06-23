---
name: memory-setup
description: >
  This skill should be used when the user wants to set up open-memory for the first
  time, connect a new machine to an existing memory network, or re-initialise after
  a broken setup. Trigger phrases include: "set up open-memory", "init memory sync",
  "connect this machine to my brain", "join my memory network", "/memory-setup".
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash, Read, Write, AskUserQuestion
metadata:
  version: "0.1.0"
---

# memory-setup

Set up open-memory on this machine. Handles both cases automatically:
- **First time ever**: create a new Git repo and push the initial brain snapshot
- **Joining existing network**: clone the remote, merge with any local state

## Step 1 — Check state

```bash
BRAIN_PY="${CLAUDE_PLUGIN_ROOT}/scripts/brain.py"
CONFIG="$HOME/.claude/open-memory-config.json"

python3 "$BRAIN_PY" machine-id
python3 "$BRAIN_PY" status
```

If `~/.claude/open-memory-config.json` already exists, tell the user their current
setup and ask if they want to re-initialise or join a different remote. Offer to
run `/memory-sync` instead if everything looks healthy.

## Step 2 — Check dependencies

```bash
command -v git >/dev/null 2>&1 && echo "git: ok" || echo "git: MISSING — install git first"
command -v python3 >/dev/null 2>&1 && echo "python3: ok" || echo "python3: MISSING"
```

If anything is missing, stop and tell the user what to install.

## Step 3 — Security notice + get the remote URL

Before asking for the remote, inform the user exactly what will be synced:

> **What open-memory exports to Git:**
> - `CLAUDE.md`, `rules/`, `skills/`, `agents/` — your instructions and workflows
> - `memory/` — patterns and notes accumulated from sessions
> - `settings.json` — hooks, permissions, MCP server command/args (**env vars with API keys are stripped**)
> - `keybindings.json`
>
> **What is NEVER exported:**
> OAuth tokens · API keys in env vars · `~/.claude.json` · session transcripts · any key/value whose name matches `api_key`, `token`, `secret`, `password`, or `credential`
>
> Memory files may contain information from your conversations. Review `~/.claude/memory/` if you have concerns before proceeding.

Then ask the user for their Git remote URL (e.g. `git@github.com:you/open-memory.git`).

Security check: if the URL looks like a public GitHub repo (no `.git` private indicator
or matches common public patterns), warn them:
> "⚠ This looks like it could be a public repository. Your CLAUDE.md, memory, rules,
> and skills will be stored there. Please make sure the repo is private before continuing."

Ask for confirmation before proceeding.

## Step 3b — Scan for secrets before export

Before exporting any local state to the repo, scan for secrets that shouldn't be committed:

```bash
SCAN_RESULT=$(python3 "$BRAIN_PY" scan)
WARNINGS=$(echo "$SCAN_RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['warnings']))")

if [ "$WARNINGS" -gt 0 ]; then
  echo "⚠ Secret scan found $WARNINGS potential issue(s) in your memory files:"
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

## Step 4 — Detect: new network or joining?

```bash
# Try fetching the remote — if it succeeds and has content, we're joining
git ls-remote "$REMOTE_URL" HEAD 2>/dev/null && echo "remote-exists" || echo "remote-empty"
```

**If remote is empty → new network:**

```bash
REPO="$HOME/.claude/open-memory-repo"
mkdir -p "$REPO/machines" "$REPO/consolidated" "$REPO/meta"
cd "$REPO"
git init
git remote add origin "$REMOTE_URL"

# Export current local state
MACHINE_ID=$(python3 "$BRAIN_PY" machine-id)
python3 "$BRAIN_PY" export > "$REPO/machines/$MACHINE_ID.json"
cp "$REPO/machines/$MACHINE_ID.json" "$REPO/consolidated/brain.json"

echo '{"syncs":[]}' > "$REPO/meta/sync-log.json"

git add .
git commit -m "init: $(python3 "$BRAIN_PY" machine-id) on $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git branch -M main
git push -u origin main
```

**If remote has content → joining:**

```bash
REPO="$HOME/.claude/open-memory-repo"

# Back up current state before touching anything
BACKUP="$HOME/.claude/open-memory-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
python3 "$BRAIN_PY" export > "$BACKUP/pre-join-snapshot.json"
echo "Backup saved to $BACKUP"

# Clone the remote (or pull if the dir already exists from a prior attempt)
if [ -d "$REPO/.git" ]; then
  git -C "$REPO" pull origin main
else
  git clone "$REMOTE_URL" "$REPO"
fi

MACHINE_ID=$(python3 "$BRAIN_PY" machine-id)
python3 "$BRAIN_PY" export > "$REPO/machines/$MACHINE_ID.json"
```

Ask the user how to handle existing local content:
- **Merge (recommended)** — combine local + network using smart merge
- **Keep mine** — push local snapshot, keep local files as-is
- **Take theirs** — replace local state with the consolidated network brain

For "Merge": merge the two snapshots and apply:
```bash
python3 "$BRAIN_PY" merge \
  "$REPO/machines/$MACHINE_ID.json" \
  "$REPO/consolidated/brain.json" \
  > /tmp/open-memory-merged.json

python3 "$BRAIN_PY" import /tmp/open-memory-merged.json
```

For "Keep mine": push the local snapshot without importing remote content:
```bash
# Local files stay unchanged — just register this machine in the network.
# The local snapshot was already exported above; nothing else to import.
echo "Keeping local state — will push this machine's snapshot to the network."
```

For "Take theirs":
```bash
python3 "$BRAIN_PY" import "$REPO/consolidated/brain.json"
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
    "machine_id": "$(python3 "$BRAIN_PY" machine-id)",
    "last_sync": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
Path(os.path.expanduser("~/.claude/open-memory-config.json")).write_text(json.dumps(cfg, indent=2))
print("Config saved.")
EOF
```

## Step 5b — Log the setup event

```bash
python3 "$BRAIN_PY" log-sync "$HOME/.claude/open-memory-repo" "setup" "machine joined network"
```

## Step 6 — Confirm

Tell the user:
- Their machine ID
- The remote URL
- How many machines are now in the network (`ls $REPO/machines/ | wc -l`)
- What was imported (output from `python3 "$BRAIN_PY" status`)
- Next step: "Run `/memory-sync` any time you want to sync. Run `/memory-manage`
  to check network status, promote memory, or share skills."
