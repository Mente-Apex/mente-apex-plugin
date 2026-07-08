---
name: config-sync-manage
description: >
  This skill should be used when the user wants to inspect their config-sync repo,
  promote accumulated session notes into permanent rules or CLAUDE.md, share a
  skill or rule with other machines, or see sync history. Trigger phrases include:
  "config sync status", "promote my notes to rules", "share this skill",
  "share this rule", "how many machines", "what did I sync recently",
  "/config-sync-manage", "manage config sync".
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
metadata:
  version: "0.3.1"
---

# config-sync-manage

Everything except setup and sync, for **Claude config sync**. Three sub-actions —
detect what the user wants and jump to the right section.

> **Not the knowledge brain.** This manages the *config-sync* repo (CLAUDE.md, rules,
> skills, agents, memory files synced across machines). For capturing/recalling facts
> use **Mente Apex memory** (the `mem` CLI / the `mente-apex-memory` MCP server) — a different system.

| User intent | Section |
|---|---|
| "show me status / what's synced / how many machines" | → Status |
| "promote notes / graduate notes to rules / evolve" | → Promote |
| "share a skill / share a rule / share an agent" | → Share |

---

## Status

Show a clear picture of the network and local config-sync state.

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
s = json.loads(Path(sys.argv[1]).read_text())
ts = s.get("timestamp", "unknown")[:19].replace("T", " ")
print(f"  {s['machine_id']:<35} last snapshot: {ts}")
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
    print("  (none yet — use /config-sync-manage share to add)")
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
    ts   = entry.get("timestamp", "?")[:19].replace("T", " ")
    mid  = entry.get("machine_id", "?")
    act  = entry.get("action", "sync")
    summ = entry.get("summary", "")
    line = f"  {ts}  [{act:<8}]  {mid}"
    if summ:
        line += f"  — {summ}"
    print(line)
EOF
fi
```

Present the output cleanly. If the repo doesn't exist yet, remind the user to run
`/config-sync-setup` first.

If the user asks for the **full** log (e.g. "show all my syncs"), read the complete
`sync-log.json` and paginate or show all entries without the `-10` limit.

---

## Promote

Analyse accumulated memory and suggest graduating repeated patterns to permanent config.

This is the answer to "Claude keeps forgetting X" — instead of repeating yourself
every session, a pattern gets written once into CLAUDE.md or a rules file and is
always in context from then on.

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
echo "Analysing memory for promotion candidates..."
python3 "$ENGINE" promote
```

Parse the JSON output (`{"suggestions": [...]}`).

If no suggestions: "No strong promotion candidates found yet — keep using Claude
and run this again when more memory has accumulated."

For each suggestion, present it clearly:

```
── Suggestion 1 of N ────────────────────────────────
Type   : CLAUDE.md addition   (or: new rule file)
Reason : <reason from the analysis>

Content to add:
────────────────
<content>
────────────────

Accept / Skip / Edit
```

**If accepted:**

For `claude_md` type:
```bash
# Capture the date in bash first so it expands correctly inside the Python heredoc
PROMOTE_DATE=$(date +%Y-%m-%d)
python3 - "$PROMOTE_DATE" <<'PYEOF'
import sys
from pathlib import Path
promote_date = sys.argv[1]
p = Path.home() / ".claude" / "CLAUDE.md"
existing = p.read_text() if p.exists() else ""
addition = f"""
## [Promoted from memory — {promote_date}]
<content>
"""
p.write_text(existing.rstrip() + "\n\n" + addition.strip() + "\n")
print("Added to CLAUDE.md")
PYEOF
```

For `rule` type — ask the user for a short filename (e.g. `python-style`), then:
```bash
python3 - <<EOF
from pathlib import Path
rules_dir = Path.home() / ".claude" / "rules"
rules_dir.mkdir(exist_ok=True)
rule_file = rules_dir / "<filename>.md"
rule_file.write_text("<content>\n")
print(f"Created rule: {rule_file}")
EOF
```

For "Edit": show the content in the conversation, let the user type their revised
version, then apply that instead.

After handling all suggestions, offer to sync the changes: "Promotion complete.
Run `/config-sync` to push these permanent rules to your other machines."

---

## Share

> **Skills & agents auto-propagate now.** Since config-sync v0.6.0 every local
> `~/.claude/skills/` and `~/.claude/agents/` entry is exported as a hash-gated bundle
> on each `/config-sync` — you no longer need to share them explicitly. `share` remains
> useful for **rules**, and as an explicit, reviewable alternative for skills/agents.
> **Plugins are not shared through this flow.** Since the marketplace propagator
> landed, every `/config-sync` records this machine's installed plugins in a
> desired-state manifest, and `plugins-plan` / `plugins-apply` refresh marketplaces
> and install/update plugins on other machines automatically (with your consent).

Copy a local skill, agent, or rule into the repo's `shared/` namespace so
other machines in the network receive it on their next sync.

Ask the user what they want to share if not already specified:
- Type: skill / agent / rule
- Name: the filename (e.g. `refactor`, `code-reviewer.md`, `python-style.md`)

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
CLAUDE_DIR="$HOME/.claude"

TYPE="<skill|agent|rule>"
NAME="<name>"

# Plugins converge automatically now — there is no manual plugin-share step. On
# every /config-sync, propagate-export records this machine's installed plugins in
# a desired-state manifest, and plugins-plan / plugins-apply refresh marketplaces
# and install/update them on other machines (after you approve the plan). Only
# skills, agents, and rules are shared through this flow.
if [ "$TYPE" = "plugin" ]; then
  echo "Plugins sync automatically — run /config-sync on each machine; no manual share needed."
  exit 0
fi

# Resolve source path
case "$TYPE" in
  skill)   SRC="$CLAUDE_DIR/skills/$NAME" ;;
  agent)   SRC="$CLAUDE_DIR/agents/$NAME" ;;
  rule)    SRC="$CLAUDE_DIR/rules/$NAME" ;;
esac

if [ ! -e "$SRC" ]; then
  echo "Not found: $SRC"
  echo "Available ${TYPE}s:"
  ls "$CLAUDE_DIR/${TYPE}s/" 2>/dev/null || echo "  (none)"
  exit 1
fi
```

Show the user a preview of what will be shared (the first 20 lines of the main
file), then ask for confirmation.

```bash
mkdir -p "$REPO/shared/${TYPE}s"
cp -r "$SRC" "$REPO/shared/${TYPE}s/"

cd "$REPO"
git add shared/
git commit -m "share: $TYPE/$NAME from $(python3 "$ENGINE" machine-id)"
git push origin main 2>&1 && \
  echo "✓ $TYPE '$NAME' shared — other machines will receive it on next sync." || \
  echo "⚠ Shared locally but push failed. Run /config-sync to retry."
```

---

## A note on deletions

**Bundle deletions propagate; config deletions don't.** Skill/agent **bundles**
now carry deletion tombstones: delete a skill on one machine and, on the next
`/config-sync`, other machines are *prompted* to remove it (via `resolve-deletion`).
**Config** — CLAUDE.md, `memory/`, `rules/`, and anything copied into `shared/` via
**Share** above — is still **union-only**: promoting and sharing *add* content that
propagates, but **deleting** does not. A memory, rule, or shared artifact you remove
on one machine is resurrected from another machine's snapshot (and from
`consolidated/snapshot.json`) on the next sync. To remove config content
everywhere: delete it on **every** machine **and** from `consolidated/snapshot.json`
+ each `machines/*.json`, then re-push.

