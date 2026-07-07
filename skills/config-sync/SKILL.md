---
name: config-sync
description: >
  This skill should be used when the user wants to sync their Claude config across
  machines, push local config changes to the remote, pull updates from other machines,
  or resolve merge conflicts between machines. Trigger phrases include: "sync my Claude
  config", "push my config", "pull config from other machines", "sync with my other
  machines", "my config is out of date", "/config-sync".
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
metadata:
  version: "0.8.0"
---

# config-sync

The daily sync cycle for your Claude config: export local state → push → pull →
smart-merge → apply. Plugins are synced too: marketplace plugins converge via a
desired-state manifest — `plugins-plan` proposes marketplace refreshes and
installs/updates, and nothing is applied until you approve it in Step 4b.
Conflict resolution happens inline — no separate command needed.

> **Not the knowledge brain.** This syncs your `~/.claude` *config files* across
> machines. For capturing/recalling facts use **Mente Apex memory** (the `mem` CLI /
> the `mente-apex-memory` MCP server) — a different system with its own `mem sync`.

## Step 0 — Verify setup

```bash
ENGINE="${CLAUDE_PLUGIN_ROOT:-}/scripts/config_sync.py"
if [ ! -f "$ENGINE" ]; then
  # CLAUDE_PLUGIN_ROOT is unset outside plugin context (e.g. a standalone-copied
  # skill) — fall back to the installed plugin cache.
  for candidate in "$HOME/.claude/plugins/cache/"*/mente-apex/*/scripts/config_sync.py; do
    [ -f "$candidate" ] && ENGINE="$candidate" && break
  done
fi
[ -f "$ENGINE" ] || { echo "config_sync.py engine not found — run: claude plugin install mente-apex"; exit 1; }
CONFIG="$HOME/.claude/config-sync-config.json"
REPO="$HOME/.claude/config-sync-repo"

# One-time, idempotent rename of any legacy open-memory-* paths. No-op otherwise.
python3 "$ENGINE" migrate

if [ ! -f "$CONFIG" ]; then
  echo "config sync is not set up yet. Run /config-sync-setup first."
  exit 1
fi

MACHINE_ID=$(python3 "$ENGINE" machine-id)
```

## Step 1 — Scan for secrets, then export and push local state

Before exporting, scan for any secret-like content that shouldn't be committed.
`scan --gate` prints any findings and exits non-zero when the config isn't clean:

```bash
if python3 "$ENGINE" scan --gate; then
  SCAN_CLEAN=1
else
  SCAN_CLEAN=0
fi
```

If `SCAN_CLEAN` is `0`, the findings were printed above — use **AskUserQuestion**
to ask whether to continue anyway. If the user declines, stop here. If they accept
(or the scan was clean), proceed:

```bash
# Reconcile first (mutating): drop orphaned plugin flags + prune stale caches.
# Kept separate from export so export/backup stay pure, side-effect-free queries.
python3 "$ENGINE" reconcile

# Export through the propagator seam: writes the machine snapshot (config —
# CLAUDE.md/memory/rules/settings) AND skill/agent bundles under bundles/
# (all files, hash-gated). Replaces the old `export > machines/…` line.
EXPORT_OUT=$(python3 "$ENGINE" propagate-export "$REPO")
echo "$EXPORT_OUT"

# Surface plugin-provenance warnings: plugins that can't reach your other machines
# because their marketplace isn't a shareable git/GitHub remote.
echo "$EXPORT_OUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    data = {}
for warning in data.get('marketplace', {}).get('warnings', []):
    print('⚠ ' + warning)
"
```

> If any `⚠` lines appeared, tell the user those plugins won't sync to their other
> machines and suggest publishing each to a GitHub marketplace. This is advisory
> only — **do not** stop the sync; continue to the next step.

```bash
cd "$REPO"
git add machines/ bundles/ plugins/
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
resolve them by keeping the remote's `consolidated/snapshot.json` and re-running this skill.

## Step 3 — Consolidate all machine snapshots (timestamp-ordered, most-recent-wins)

Fold every machine snapshot into the consolidated snapshot in one pass. The engine
reads all `machines/*.json` plus the existing consolidated snapshot, sorts them by
`timestamp` ascending (so the most recent snapshot is applied last and its scalar
values win), and merges entirely in-process — no predictable `/tmp` temp files and
no dependence on filename sort order. This is where diverged CLAUDE.md / memory
files get combined intelligently.

```bash
python3 "$ENGINE" consolidate "$REPO"
```

> **Deletions don't propagate.** The merge is **union-only** — there are no deletion
> tombstones. `import` only writes/updates files and never deletes; `merge` unions keys,
> JSON lists, and markdown sections. So a memory or rule you delete on one machine is
> *resurrected* from another machine's snapshot and from `consolidated/snapshot.json` on
> the next sync. To remove something everywhere: delete it on **every** machine **and**
> from `consolidated/snapshot.json` + each `machines/*.json`, then re-push.

## Step 4 — Backup, then apply through the propagator seam

Always back up before touching local state so the user has a rollback path.

```bash
BACKUP_PATH=$(python3 "$ENGINE" backup)
echo "Backup saved: $BACKUP_PATH"

# Applies config (SnapshotPropagator: consolidated snapshot → CLAUDE.md/memory/rules/
# settings) AND skill/agent bundles (ContentBundlePropagator). Prints per-propagator
# {applied, skipped, conflicts}. Replaces the old standalone `import`.
APPLY=$(python3 "$ENGINE" propagate-apply "$REPO")
echo "$APPLY"
```

Parse `$APPLY` and tell the user which config files and which skill/agent bundles were
applied vs already up to date.

**Resolve bundle conflicts (if any).** For each entry in `content-bundle.conflicts` — a
skill/agent that differs between this machine and the network — ask the user with
**AskUserQuestion** ("Skill/agent `<name>` differs between this machine and the network —
keep your local version, or take the network's?"), then apply their choice:

```bash
# winner is "local" (keep this machine's) or "repo" (take the network's)
python3 "$ENGINE" resolve-bundle "$REPO" "<kind>" "<name>" "<winner>"
```

## Step 4b — Converge marketplace plugins (plan → consent → apply)

Skills/agents flow through `propagate-apply` (above); config through the snapshot
propagator. **Plugins** converge here from the desired-state manifest. First compute
the plan (pure — nothing is mutated):

```bash
PLAN=$(python3 "$ENGINE" plugins-plan "$REPO")
echo "$PLAN"
```

Parse `$PLAN`. If `.actions` is empty, tell the user "plugins already up to date" and
continue. Otherwise render the actions (each has `verb` + `target`) and ask with
**AskUserQuestion**: "Apply these plugin changes? — refresh N marketplace(s),
install M, update K plugin(s)." Also surface any `.skipped` entries (e.g. a
marketplace whose source is unknown).

If the user declines, stop here — nothing has been changed. If they accept, execute:

```bash
APPLIED_PLUGINS=$(python3 "$ENGINE" plugins-apply "$REPO")
echo "$APPLIED_PLUGINS"
```

Parse `.outcomes` and report which plugins were installed/updated; surface any
`ok:false` entries with their `message`. Remind the user to restart Claude to
activate newly installed plugins.

Finally, install any **legacy** shared skills/rules/agents from older machines
(never overwriting local copies):

```bash
SHARED_RESULT=$(python3 "$ENGINE" apply-shared "$REPO")
echo "$SHARED_RESULT"
```

## Step 5 — Commit the updated consolidated snapshot and push

```bash
cd "$REPO"
git add consolidated/
git diff --cached --quiet && echo "consolidated snapshot unchanged" || \
  git commit -m "merge: consolidated at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

git push origin main 2>&1
```

## Step 6 — Write sync log entry and update config

```bash
# Summarise what changed for the log (sum applied entries across both propagators)
APPLIED=$(echo "$APPLY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(sum(len(section.get('applied',[])) for section in d.values()))" 2>/dev/null || echo "?")
SHARED_IN=$(echo "$SHARED_RESULT" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['installed']))" 2>/dev/null || echo "0")

python3 "$ENGINE" log-sync "$REPO" "sync" "$APPLIED file(s) updated, $SHARED_IN shared artifact(s) installed"

# Update last_sync timestamp in local config
python3 - <<EOF
import json
from pathlib import Path
from datetime import datetime, timezone
cfg_path = Path.home() / ".claude" / "config-sync-config.json"
cfg = json.loads(cfg_path.read_text())
cfg["last_sync"] = datetime.now(timezone.utc).isoformat()
cfg_path.write_text(json.dumps(cfg, indent=2))
EOF
```

## Step 7 — Summary

Show the user a clean summary:

```
✓ Config synced
  Pushed   : <N> local change(s), <N> plugin(s) exported
  Pulled   : <N> remote commit(s)
  Merged   : <list of files that changed>
  Plugins  : <N> plugin(s) installed/updated via consent (or "none")
  MCP servers: <N> new server(s) added (or "none new")
  Network  : <N> machine(s) in sync
  Last sync: <timestamp>
```

If new plugins were installed, remind the user to restart Claude to activate them.
If new MCP servers were added, remind the user to restart Claude to load them.

If nothing changed on either side: "✓ Already up to date — nothing to sync."

## Handling real conflicts

A "conflict" in config-sync terms means two machines have edited the same file
in ways the LLM merge found irreconcilable. This should be rare.

If `config_sync.py merge` returns a file with `<<<<<<` markers (fallback case), surface
each conflict to the user directly in the conversation:

```
⚠ Conflict in CLAUDE.md — two versions couldn't be auto-merged:

── Machine A says ────────────────
<content>

── Machine B says ────────────────
<content>

Which should win? (A / B / let me write my own)
```

Once the user provides a resolution, write it into the consolidated snapshot and re-apply locally before committing:

```bash
# Write the resolved content into $REPO/consolidated/snapshot.json
# (replace the conflicted section with the chosen version), then re-apply so
# local files reflect the resolution.
python3 "$ENGINE" propagate-apply "$REPO"
```

Then continue to Step 5 (commit and push the resolved consolidated snapshot).
