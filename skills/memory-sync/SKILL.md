---
name: memory-sync
description: >
  This skill should be used when the user wants to sync their memory across machines,
  push local changes to the remote, pull updates from other machines, or resolve
  merge conflicts between machines. Trigger phrases include: "sync my memory",
  "push my brain", "pull from remote", "sync with other machines",
  "my memory is out of date", "/memory-sync".
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash, Read, Write, Edit
metadata:
  version: "0.3.1"
---

# memory-sync

The daily sync cycle: export local state → push → pull → smart-merge → apply.
Plugins are synced too: local plugins are exported to `shared/plugins/` so other
machines pick them up automatically via `apply-shared`. Conflict resolution
happens inline — no separate command needed.

## Step 0 — Verify setup

```bash
BRAIN_PY="${CLAUDE_PLUGIN_ROOT}/scripts/brain.py"
CONFIG="$HOME/.claude/open-memory-config.json"
REPO="$HOME/.claude/open-memory-repo"

if [ ! -f "$CONFIG" ]; then
  echo "open-memory is not set up yet. Run /memory-setup first."
  exit 1
fi

REMOTE=$(python3 -c "import json; print(json.load(open('$CONFIG'))['remote'])")
MACHINE_ID=$(python3 "$BRAIN_PY" machine-id)
```

## Step 1 — Scan for secrets, then export and push local state

Before exporting, scan for any secret-like content that shouldn't be committed:

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

If the user confirms or there are no warnings, proceed:

```bash
# Snapshot current local brain
python3 "$BRAIN_PY" export > "$REPO/machines/$MACHINE_ID.json"
```

Then export installed plugins to `shared/plugins/` so other machines can install them
via `apply-shared`. Each plugin gets its own subdirectory named by its key, containing a
`plugin-meta.json` and a copy of all its cache files. Plugins already present in
`shared/plugins/` are skipped — only new ones are added.

```bash
python3 - <<'PYEOF'
import json, shutil
from pathlib import Path

claude_dir = Path.home() / ".claude"
installed_path = claude_dir / "plugins" / "installed_plugins.json"
shared_plugins = Path("$REPO/shared/plugins")
shared_plugins.mkdir(parents=True, exist_ok=True)

if not installed_path.exists():
    print("No installed_plugins.json found — skipping plugin export")
    exit(0)

data = json.loads(installed_path.read_text())
for plugin_key, entries in data.get("plugins", {}).items():
    plugin_dest = shared_plugins / plugin_key
    if plugin_dest.exists():
        print(f"skip (already shared): {plugin_key}")
        continue

    entry = entries[0] if isinstance(entries, list) else entries
    install_path = Path(entry["installPath"])

    # Derive marketplace + name from the key (format: name@marketplace)
    parts = plugin_key.split("@", 1)
    name = parts[0]
    marketplace = parts[1] if len(parts) > 1 else "unknown"
    version = entry.get("version", "unknown")

    plugin_dest.mkdir(parents=True, exist_ok=True)

    # Write plugin-meta.json — brain.py's apply-shared reads this to register the plugin
    meta = {
        "key": plugin_key,
        "name": name,
        "marketplace": marketplace,
        "version": version,
    }
    if entry.get("gitCommitSha"):
        meta["gitCommitSha"] = entry["gitCommitSha"]
    (plugin_dest / "plugin-meta.json").write_text(json.dumps(meta, indent=2))

    # Copy all plugin files from the local cache so apply-shared can install them
    if install_path.exists():
        for src in sorted(install_path.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(install_path)
            dest = plugin_dest / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        print(f"exported: {plugin_key} ({version})")
    else:
        print(f"exported meta only (cache missing): {plugin_key}")
PYEOF
```

```bash
cd "$REPO"
git add machines/ shared/plugins/
git diff --cached --quiet && echo "no local changes" || \
  git commit -m "sync: $MACHINE_ID at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

git push origin main 2>&1
```

If push fails (e.g. remote has diverged), note it and continue — pull will fix it.

## Step 2 — Pull remote changes

```bash
cd "$REPO"
git fetch origin main 2>&1

# Check if remote has anything new
BEHIND=$(git rev-list HEAD..origin/main --count 2>/dev/null || echo 0)
echo "Remote is $BEHIND commit(s) ahead of local"

git pull origin main --no-rebase 2>&1
```

If `git pull` produces merge conflicts in the repo itself (unlikely but possible),
resolve them by keeping the remote's `consolidated/brain.json` and re-running this skill.

## Step 3 — Smart-merge all machine snapshots into consolidated brain

Read all machine snapshots and merge them one by one into the consolidated brain.
This is where diverged CLAUDE.md / memory files get combined intelligently.

```bash
CONSOLIDATED="$REPO/consolidated/brain.json"

# Always merge our own snapshot into the consolidated brain first.
# The consolidated brain is not guaranteed to already contain our latest local state —
# e.g. on first join, after a reset, or if the consolidated brain drifted. Merging
# our snapshot in explicitly ensures MCP servers, settings, and other local data
# are never silently dropped.
python3 "$BRAIN_PY" merge "$CONSOLIDATED" "$REPO/machines/$MACHINE_ID.json" > /tmp/open-memory-base.json

# Merge in each other machine's snapshot
for snap in "$REPO/machines/"*.json; do
  mid=$(python3 -c "import json; print(json.load(open('$snap'))['machine_id'])")
  if [ "$mid" = "$MACHINE_ID" ]; then
    continue  # already merged above
  fi
  echo "Merging snapshot from: $mid"
  python3 "$BRAIN_PY" merge /tmp/open-memory-base.json "$snap" > /tmp/open-memory-merged.json
  cp /tmp/open-memory-merged.json /tmp/open-memory-base.json
done

cp /tmp/open-memory-base.json "$CONSOLIDATED"
```

## Step 4 — Backup, then apply merged brain locally

Always back up before touching local state so the user has a rollback path.

```bash
BACKUP_PATH=$(python3 "$BRAIN_PY" backup)
echo "Backup saved: $BACKUP_PATH"

RESULT=$(python3 "$BRAIN_PY" import "$CONSOLIDATED")
echo "$RESULT"
```

Parse the JSON result and tell the user clearly:
- How many files were updated vs already up to date
- Which specific files changed (CLAUDE.md? memory/? rules/?)

## Step 4b — Apply shared artifacts from the network

Other machines may have pushed skills, rules, agents, or plugins to `shared/`.
Install any that aren't already present locally. Skills/rules/agents are never
overwritten; plugins are registered only if absent from `installed_plugins.json`.

```bash
SHARED_RESULT=$(python3 "$BRAIN_PY" apply-shared "$REPO")
echo "$SHARED_RESULT"
```

Parse and mention any newly installed shared artifacts to the user, calling out
plugins specifically (e.g. "Installed 2 new plugin(s): playwright@claude-plugins-official,
superpowers@claude-plugins-official — restart Claude to activate them").

## Step 5 — Commit the updated consolidated brain and push

```bash
cd "$REPO"
git add consolidated/
git diff --cached --quiet && echo "consolidated brain unchanged" || \
  git commit -m "merge: consolidated at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

git push origin main 2>&1
```

## Step 6 — Write sync log entry and update config

```bash
# Summarise what changed for the log (count applied files from import result)
APPLIED=$(echo "$RESULT" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['applied']))" 2>/dev/null || echo "?")
SHARED_IN=$(echo "$SHARED_RESULT" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['installed']))" 2>/dev/null || echo "0")

python3 "$BRAIN_PY" log-sync "$REPO" "sync" "$APPLIED file(s) updated, $SHARED_IN shared artifact(s) installed"

# Update last_sync timestamp in local config
python3 - <<EOF
import json
from pathlib import Path
from datetime import datetime, timezone
cfg_path = Path.home() / ".claude" / "open-memory-config.json"
cfg = json.loads(cfg_path.read_text())
cfg["last_sync"] = datetime.now(timezone.utc).isoformat()
cfg_path.write_text(json.dumps(cfg, indent=2))
EOF
```

## Step 7 — Summary

Show the user a clean summary:

```
✓ Memory synced
  Pushed   : <N> local change(s), <N> plugin(s) exported
  Pulled   : <N> remote commit(s)
  Merged   : <list of files that changed>
  Plugins  : <N> new plugin(s) installed (or "none new")
  MCP servers: <N> new server(s) added (or "none new")
  Network  : <N> machine(s) in sync
  Last sync: <timestamp>
```

If new plugins were installed, remind the user to restart Claude to activate them.
If new MCP servers were added, remind the user to restart Claude to load them.

If nothing changed on either side: "✓ Already up to date — nothing to sync."

## Handling real conflicts

A "conflict" in open-memory terms means two machines have edited the same file
in ways the LLM merge found irreconcilable. This should be rare.

If `brain.py merge` returns a file with `<<<<<<` markers (fallback case), surface
each conflict to the user directly in the conversation:

```
⚠ Conflict in CLAUDE.md — two versions couldn't be auto-merged:

── Machine A says ────────────────
<content>

── Machine B says ────────────────
<content>

Which should win? (A / B / let me write my own)
```

Once the user provides a resolution, write it into the consolidated brain and re-apply locally before committing:

```bash
# Write the resolved content into the consolidated brain file
# (replace the conflicted section with the chosen version)
# Then re-import so local files reflect the resolution
python3 "$BRAIN_PY" import "$CONSOLIDATED"
```

Then continue to Step 5 (commit and push the resolved consolidated brain).
