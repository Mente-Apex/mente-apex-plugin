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
  version: "0.2.1"
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
  # skill) — fall back to the installed plugin cache.
  for candidate in "$HOME/.claude/plugins/cache/"*/mente-apex/*/scripts/config_sync.py; do
    [ -f "$candidate" ] && ENGINE="$candidate" && break
  done
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
found = False
for type_dir in sorted(shared.iterdir()):
    if not type_dir.is_dir():
        continue
    for path in sorted(type_dir.rglob("*")):
        if path.is_file():
            found = True
            rel = path.relative_to(shared)
            git_info = subprocess.run(
                ["git", "log", "--format=%an|%ad", "--date=short", "-1", "--", f"shared/{rel}"],
                cwd=repo, capture_output=True, text=True
            ).stdout.strip() or "unknown|unknown"
            parts = git_info.split("|")
            author = parts[0] if parts else "unknown"
            date = parts[1] if len(parts) > 1 else "unknown"
            print(f"  {str(rel):<40}  shared by {author} on {date}")
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
  # skill) — fall back to the installed plugin cache.
  for candidate in "$HOME/.claude/plugins/cache/"*/mente-apex/*/scripts/config_sync.py; do
    [ -f "$candidate" ] && ENGINE="$candidate" && break
  done
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

Copy a local skill, agent, rule, or plugin into the repo's `shared/` namespace so
other machines in the network receive it on their next sync.

Ask the user what they want to share if not already specified:
- Type: skill / agent / rule / plugin
- Name: the filename or plugin key (e.g. `refactor`, `code-reviewer.md`, `python-style.md`, `mente-apex@mente-apex`)

For `plugin`, list what is available from `installed_plugins.json` if the user hasn't specified:

```bash
CLAUDE_DIR="$HOME/.claude"
python3 - <<'EOF'
import json
from pathlib import Path
p = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
if not p.exists():
    print("No installed_plugins.json found.")
else:
    data = json.loads(p.read_text())
    plugins = data.get("plugins", {})
    if not plugins:
        print("No plugins installed.")
    else:
        print("Installed plugins:")
        for plugin_key, entries in plugins.items():
            entry = entries[0] if entries else {}
            version = entry.get("version", "unknown")
            print(f"  {plugin_key}  (v{version})")
EOF
```

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
REPO="$HOME/.claude/config-sync-repo"
CLAUDE_DIR="$HOME/.claude"

TYPE="<skill|agent|rule|plugin>"
NAME="<name>"

# Resolve source path
case "$TYPE" in
  skill)   SRC="$CLAUDE_DIR/skills/$NAME" ;;
  agent)   SRC="$CLAUDE_DIR/agents/$NAME" ;;
  rule)    SRC="$CLAUDE_DIR/rules/$NAME" ;;
  plugin)
    # NAME is a plugin key like "mente-apex@mente-apex"
    SRC=$(python3 - "$NAME" <<'EOF'
import json, sys
from pathlib import Path
plugin_key = sys.argv[1]
p = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
if not p.exists():
    print("")
    sys.exit(1)
data = json.loads(p.read_text())
entries = data.get("plugins", {}).get(plugin_key, [])
if not entries:
    print("")
    sys.exit(1)
print(entries[0].get("installPath", ""))
EOF
    )
    ;;
esac

if [ ! -e "$SRC" ]; then
  echo "Not found: $SRC"
  if [ "$TYPE" = "plugin" ]; then
    echo "Available plugins:"
    python3 - <<'EOF'
import json
from pathlib import Path
p = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
data = json.loads(p.read_text()) if p.exists() else {}
for key in data.get("plugins", {}):
    print(f"  {key}")
EOF
  else
    echo "Available ${TYPE}s:"
    ls "$CLAUDE_DIR/${TYPE}s/" 2>/dev/null || echo "  (none)"
  fi
  exit 1
fi
```

Show the user a preview of what will be shared:
- For skills/agents/rules: first 20 lines of the main file
- For plugins: list the top-level files in the install directory

Then ask for confirmation.

```bash
if [ "$TYPE" = "plugin" ]; then
  # Write plugin files + a plugin-meta.json into shared/plugins/<NAME>/
  PLUGIN_KEY="$NAME"
  DEST_DIR="$REPO/shared/plugins/$PLUGIN_KEY"
  mkdir -p "$DEST_DIR"
  cp -r "$SRC/." "$DEST_DIR/"

  # Write plugin-meta.json so apply-shared can register it on other machines.
  # Reuse the engine's guarded _derive_plugin_meta so a dev/linked install
  # (installPath without a 'cache' segment) never crashes with StopIteration.
  python3 - "$PLUGIN_KEY" "$DEST_DIR" "$(dirname "$ENGINE")" <<'EOF'
import json, sys
from pathlib import Path
plugin_key = sys.argv[1]
dest_dir = Path(sys.argv[2])
sys.path.insert(0, sys.argv[3])
from config_sync import _derive_plugin_meta
installed = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
entries = json.loads(installed.read_text())["plugins"][plugin_key]
entry = entries[0] if isinstance(entries, list) else entries
meta = _derive_plugin_meta(plugin_key, entry)
(dest_dir / "plugin-meta.json").write_text(json.dumps(meta, indent=2))
print(f"Wrote plugin-meta.json for {plugin_key} v{meta['version']}")
EOF

else
  mkdir -p "$REPO/shared/${TYPE}s"
  cp -r "$SRC" "$REPO/shared/${TYPE}s/"
fi

cd "$REPO"
git add shared/
git commit -m "share: $TYPE/$NAME from $(python3 "$ENGINE" machine-id)"
git push origin main 2>&1 && \
  echo "✓ $TYPE '$NAME' shared — other machines will receive it on next sync." || \
  echo "⚠ Shared locally but push failed. Run /config-sync to retry."
```

---

## A note on deletions

Config sync is **union-only** — it has no deletion tombstones. Promoting and sharing
*add* content that propagates; **deleting** does not. A memory, rule, or shared
artifact you remove on one machine is resurrected from another machine's snapshot
(and from `consolidated/snapshot.json`) on the next sync. To remove something
everywhere: delete it on **every** machine **and** from `consolidated/snapshot.json`
+ each `machines/*.json`, then re-push.

