---
name: config-sync
description: >
  This skill should be used when the user wants to sync their Claude config across
  machines, push local config changes to the remote, pull updates from other machines,
  or resolve merge conflicts between machines. Also handles read-only status: how many
  machines are in the network, what's shared, and recent sync history. Trigger phrases
  include: "sync my Claude config", "push my config", "pull config from other machines",
  "sync with my other machines", "my config is out of date", "/config-sync", "config
  sync status", "how many machines", "what did I sync recently".
user-invocable: true
disable-model-invocation: false
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
metadata:
  version: "0.9.0"
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

## Mode select — status vs full sync

If the user only wants to **see** the state of the network (e.g. "config sync status",
"how many machines", "what did I sync recently", `/config-sync status`) and *not*
actually push/pull, jump straight to **[Status (read-only)](#status-read-only)** at the
bottom, run it, and stop. It has no side effects. Otherwise, run the full sync cycle
below (Steps 0–7).

## Step 0 — Verify setup

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
printf '%s\n' "$EXPORT_OUT"

# Surface plugin-provenance warnings: plugins that can't reach your other machines
# because their marketplace isn't a shareable git/GitHub remote.
printf '%s\n' "$EXPORT_OUT" | python3 -c "
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
>
> If `propagate-export` reported any `content-bundle.tombstoned` entries, tell the
> user which skills/agents were retired and will be proposed for removal on other
> machines.

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

> **Bundle deletions propagate; config deletions don't.** Skill/agent **bundles**
> now carry deletion tombstones: delete a skill on one machine and, on the next
> sync, other machines are *prompted* to remove it (Step 4). **Snapshot config**
> (CLAUDE.md, `memory/`, `rules/`) is still **union-only** — a memory or rule you
> delete on one machine is *resurrected* from another machine's snapshot. To remove
> config content everywhere: delete it on **every** machine **and** from
> `consolidated/snapshot.json` + each `machines/*.json`, then re-push.

## Step 4 — Backup, then apply through the propagator seam

Always back up before touching local state so the user has a rollback path.

```bash
BACKUP_PATH=$(python3 "$ENGINE" backup)
echo "Backup saved: $BACKUP_PATH"

# Applies config (SnapshotPropagator: consolidated snapshot → CLAUDE.md/memory/rules/
# settings) AND skill/agent bundles (ContentBundlePropagator). Prints per-propagator
# {applied, skipped, conflicts}. Replaces the old standalone `import`.
APPLY=$(python3 "$ENGINE" propagate-apply "$REPO")
printf '%s\n' "$APPLY"
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

**Resolve bundle deletions (if any).** For each entry in `content-bundle.deletions` —
a skill/agent the network retired that this machine still has — ask the user with
**AskUserQuestion** ("Skill/agent `<name>` was deleted on `<machine_id>` at
`<deleted_at>` — remove it here, or keep it?"), then apply their choice:

```bash
# decision is "remove" (delete this machine's copy) or "keep" (retain it; the next
# export re-adds it for everyone)
python3 "$ENGINE" resolve-deletion "$REPO" "<kind>" "<name>" "<decision>"
```

## Step 4b — Converge marketplace plugins (plan → consent → apply)

Skills/agents flow through `propagate-apply` (above); config through the snapshot
propagator. **Plugins** converge here from the desired-state manifest. First compute
the plan (pure — nothing is mutated):

```bash
PLAN=$(python3 "$ENGINE" plugins-plan "$REPO")
printf '%s\n' "$PLAN"
```

Parse `$PLAN`. If `.actions` is empty, tell the user "plugins already up to date" and
continue. Otherwise render the actions (each has `verb` + `target`) and ask with
**AskUserQuestion**: "Apply these plugin changes? — refresh N marketplace(s),
install M, update K plugin(s)." Also surface any `.skipped` entries (e.g. a
marketplace whose source is unknown).

If the user declines, stop here — nothing has been changed. If they accept, execute:

```bash
APPLIED_PLUGINS=$(python3 "$ENGINE" plugins-apply "$REPO")
printf '%s\n' "$APPLIED_PLUGINS"
```

Parse `.outcomes` and report which plugins were installed/updated; surface any
`ok:false` entries with their `message`. Remind the user to restart Claude to
activate newly installed plugins.

Finally, install any **legacy** shared skills/rules/agents from older machines
(never overwriting local copies):

```bash
SHARED_RESULT=$(python3 "$ENGINE" apply-shared "$REPO")
printf '%s\n' "$SHARED_RESULT"
```

## Step 4c — Wire declared hooks

After the plugin convergence step, provision any repo-shipped hooks this machine
is missing:

1. Run `python3 "$ENGINE" hooks-plan`. It scans the declared roots
   (`CONFIG_SYNC_ROOT_*`) for `hooks/hooks.json` files and lists the hook
   registrations missing from `~/.claude/settings.json`.
2. If `actions` is empty, say so and move on.
3. Otherwise show the user each hook it would register (event, matcher, command)
   and ask once for confirmation — this is the single consent gate.
4. On yes, run `python3 "$ENGINE" hooks-apply`. It writes each
   registration in portable `${TOKEN}` form, tagged `# config-sync:<id>` so it is
   never confused with a hand-added hook. Re-running is a safe no-op.

Never run `hooks-apply` without the user's confirmation.

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
APPLIED=$(printf '%s\n' "$APPLY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(sum(len(section.get('applied',[])) for section in d.values()))" 2>/dev/null || echo "?")
SHARED_IN=$(printf '%s\n' "$SHARED_RESULT" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['installed']))" 2>/dev/null || echo "0")

python3 "$ENGINE" log-sync "$REPO" "sync" "$APPLIED file(s) updated, $SHARED_IN shared artifact(s) installed"

# Persist the log entry. log-sync writes meta/sync-log.json but does not commit it,
# so without this the sync log never reaches the remote — it just accumulates as an
# uncommitted local change. Commit + push it now (a no-op when nothing changed).
cd "$REPO"
git add meta/
git diff --cached --quiet && echo "sync log unchanged" || \
  { git commit -m "log: sync entry for $MACHINE_ID at $(date -u +%Y-%m-%dT%H:%M:%SZ)"; git push origin main 2>&1; }

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
  Retired  : <N> skill/agent bundle(s) tombstoned or removed (or "none")
  Plugins  : <N> plugin(s) installed/updated via consent (or "none")
  MCP servers: <N> new server(s) added (or "none new")
  Network  : <N> machine(s) in sync
  Last sync: <timestamp>
```

If new plugins were installed, remind the user to restart Claude to activate them.
If new MCP servers were added, remind the user to restart Claude to load them.

If nothing changed on either side: "✓ Already up to date — nothing to sync."

## Status (read-only)

A pure inventory of the network and local config-sync state — **no push, no pull, no
apply**. This is a self-contained read-only path: it resolves the engine itself and
never runs the mutating Step 0 setup, so asking for status can't trigger a sync.

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
REPO="$HOME/.claude/config-sync-repo"

if [ ! -d "$REPO" ]; then
  echo "config sync is not set up yet. Run /config-sync-setup first."
  exit 0
fi

# Local inventory
python3 "$ENGINE" status

# Network: list all machines in the repo
if [ -d "$REPO/machines" ]; then
  echo ""
  echo "── Network machines ────────────────────────────────"
  for snap in "$REPO/machines/"*.json; do
    python3 - "$snap" <<'EOF'
import json, sys
from pathlib import Path
snapshot = json.loads(Path(sys.argv[1]).read_text())
timestamp = snapshot.get("timestamp", "unknown")[:19].replace("T", " ")
print(f"  {snapshot['machine_id']:<35} last snapshot: {timestamp}")
EOF
  done
fi

# Shared artifacts (with git author + date)
if [ -d "$REPO/shared" ]; then
  echo ""
  echo "── Shared artifacts ─────────────────────────────────"
  python3 - "$REPO" <<'EOF'
import sys, subprocess
from pathlib import Path

repo = Path(sys.argv[1])
shared = repo / "shared"
ENUMERATION_CAP = 20  # list this many files per type, then summarise the rest


def last_touch(pathspec):
    """Author/date of the most recent commit touching pathspec — one `git log`
    for the whole type dir, so attribution costs one subprocess per type rather
    than one per file (which made status O(files) subprocesses)."""
    record = subprocess.run(
        ["git", "log", "--format=%an|%ad", "--date=short", "-1", "--", pathspec],
        cwd=repo, capture_output=True, text=True,
    ).stdout.strip()
    author, _, date = record.partition("|")
    return author or "unknown", date or "unknown"


found = False
for type_dir in sorted(shared.iterdir()):
    if not type_dir.is_dir():
        continue
    files = [path for path in sorted(type_dir.rglob("*")) if path.is_file()]
    if not files:
        continue
    found = True
    type_name = type_dir.name
    author, date = last_touch(f"shared/{type_name}")
    print(f"  {type_name}: {len(files)} file(s) — last updated by {author} on {date}")
    for path in files[:ENUMERATION_CAP]:
        print(f"      {path.relative_to(shared)}")
    remaining = len(files) - ENUMERATION_CAP
    if remaining > 0:
        print(f"      … and {remaining} more")
if not found:
    print("  (none — shared artifacts are legacy; skills/agents auto-propagate now)")
EOF
fi

# Recent sync log
if [ -f "$REPO/meta/sync-log.json" ]; then
  echo ""
  echo "── Last 10 syncs ────────────────────────────────────"
  python3 - "$REPO/meta/sync-log.json" <<'EOF'
import json, sys
from pathlib import Path
log = json.loads(Path(sys.argv[1]).read_text()).get("syncs", [])
for entry in reversed(log[-10:]):
    timestamp = entry.get("timestamp", "?")[:19].replace("T", " ")
    machine_id = entry.get("machine_id", "?")
    action = entry.get("action", "sync")
    summary = entry.get("summary", "")
    line = f"  {timestamp}  [{action:<8}]  {machine_id}"
    if summary:
        line += f"  — {summary}"
    print(line)
EOF
fi
```

Present the output cleanly. If the user asks for the **full** log (e.g. "show all my
syncs"), read the complete `sync-log.json` and show all entries without the `-10` limit.

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
