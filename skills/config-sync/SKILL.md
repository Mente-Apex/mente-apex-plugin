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
  version: "0.10.0"
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

# Interpreter choice lives in bin/mente-python, not here: uv first (honouring
# the operator's own pin), a new-enough system interpreter second, and a
# diagnosis rather than a SyntaxError if neither exists. Keeping it in one file
# is why that order can change without editing every skill that runs Python.
# A function, not a variable — zsh does not word-split an unquoted expansion,
# so a multi-word PY="..." would be looked up as one long command name.
LAUNCHER="$(dirname "$(dirname "$ENGINE")")/bin/mente-python"
py() { sh "$LAUNCHER" "$@"; }

# With no pin anywhere, uv picks whatever it can find, and "whatever it can
# find" differs per machine — the drift this plugin exists to prevent. uv walks
# up from $PWD for a .python-version before falling back to the global pin, so
# this looks in the same order rather than only at the current directory.
pinned() {
  directory=$PWD
  while [ "$directory" != "/" ]; do
    [ -f "$directory/.python-version" ] && return 0
    directory=$(dirname "$directory")
  done
  [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/uv/.python-version" ]
}
# Only worth saying when uv is the thing doing the choosing. With uv absent the
# launcher has already printed the one useful instruction, and this nudge would
# contradict it — then recommend `uv python pin`, a command that machine cannot
# run.
if command -v uv >/dev/null 2>&1 && ! pinned; then
  echo "No Python pin found — uv is choosing an interpreter for you. Pin one:"
  echo "  uv python pin --global $(py -c 'import sys; print(sys.version.split()[0])')"
fi
CONFIG="$HOME/.claude/config-sync-config.json"
REPO="$HOME/.claude/config-sync-repo"

# One-time, idempotent rename of any legacy open-memory-* paths. No-op otherwise.
py "$ENGINE" migrate

if [ ! -f "$CONFIG" ]; then
  echo "config sync is not set up yet. Run /config-sync-setup first."
  exit 1
fi

MACHINE_ID=$(py "$ENGINE" machine-id)
```

## Step 1 — Scan for secrets, then export and push local state

Before exporting, scan for any secret-like content that shouldn't be committed.
`scan --gate` prints any findings and exits non-zero when the config isn't clean:

```bash
if py "$ENGINE" scan --gate; then
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
py "$ENGINE" reconcile

# Export through the propagator seam: writes the machine snapshot (config —
# CLAUDE.md/memory/rules/settings) AND skill/agent bundles under bundles/
# (all files, hash-gated). Replaces the old `export > machines/…` line.
EXPORT_OUT=$(py "$ENGINE" propagate-export "$REPO")
printf '%s\n' "$EXPORT_OUT"

# Surface export warnings:
#   marketplace — plugins that can't reach your other machines because their
#                 marketplace isn't a shareable git/GitHub remote.
#   snapshot    — content provenance degraded (this machine's previous snapshot
#                 was unreadable or malformed), so every unit was re-stamped as
#                 now and content another machine rejected may come back.
printf '%s\n' "$EXPORT_OUT" | py -c "
import json, sys
try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    data = {}
for section in ('marketplace', 'snapshot'):
    for warning in data.get(section, {}).get('warnings', []):
        print('⚠ ' + warning)
"
```

> If any `⚠` lines appeared, relay them. A **marketplace** warning means those
> plugins won't sync to their other machines — suggest publishing each to a
> GitHub marketplace. A **snapshot** warning means this export could not read its
> own previous provenance, so a rejection another machine recorded may be
> re-proposed at Step 4e; tell the user which file is unreadable. Both are
> advisory — **do not** stop the sync; continue to the next step.
>
> If `propagate-export` reported any `content-bundle.tombstoned` entries, tell the
> user which skills/agents were retired and will be proposed for removal on other
> machines.

```bash
cd "$REPO"
# `rejections/` too: this run records its own rejections later (Step 4), but a
# rejection left over from a previous run — one recorded after that run's Step 5,
# or during a run that stopped early — would otherwise never be staged by
# anything. Step 5 is what carries *this* run's rejections.
git add machines/ bundles/ plugins/
if [ -d rejections ]; then git add rejections/; fi
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
py "$ENGINE" consolidate "$REPO"
```

> **Relay any `provenance_warnings`.** `consolidate` prints a
> `provenance_warnings` list beside `rejected` and `withheld`. Prefix each line
> with `⚠` and relay it. Two classes appear, with different remedies:
>
> - **A malformed `provenance` map**, naming the machine. That machine's content
>   fell back to its export timestamp, so a rejection it should have converged
>   on may be re-proposed at Step 4e instead. Tell the user to re-export on that
>   machine — a clean export rewrites the map.
> - **A snapshot with no `machine_id`** that had content withheld from it. This
>   line names no machine, and re-exporting is not the fix: the withholding
>   cannot be attributed to anyone, so *nobody* is prompted about that content at
>   Step 4e. Tell the user which addresses were affected and that the snapshot in
>   `machines/` needs a `machine_id` before those prompts can appear.
>
> Both are advisory — **do not** stop the sync. An empty list is the normal case;
> a machine that has simply not upgraded yet produces nothing here by design.
>
> **Bundle deletions propagate; config deletions need `reject`.** Skill/agent
> **bundles** carry deletion tombstones. **Snapshot config** (CLAUDE.md,
> `memory/`, `rules/`) is union-only, so a deletion alone is *resurrected* from
> another machine's snapshot — and from the consolidated snapshot itself, which
> folds its own prior output back in. To retire config content, `reject` it:
> `--scope network` strips it from the consolidated snapshot and prompts every
> other machine, `--scope local` withholds it here without touching shared state.
>
> **Whole-file rejection of a synced config file is refused by default.**
> `reject ... snapshot-file` on `CLAUDE.md`, `settings.json`, or `keybindings.json`
> raises rather than applying, because rejecting one wholesale would silently
> stop syncing it entirely. Reject a `snapshot-section` or a `settings-key`
> instead, or pass `--force` if a whole synced file really is what you want gone.
>
> **A network rejection converges on its own, machine by machine.** Every
> export stamps each addressable unit's own `changed_at` from a hash
> comparison against that machine's previous snapshot — phase 3's per-content
> provenance — rather than the wall-clock time the export ran. A machine that
> still holds the content but has not edited it re-exports the same hash, so
> consolidate reads it as no newer than the rejection and withholds it
> without anyone answering at Step 4e. See the Step 4e note for what
> `resolve-rejection` is still for.
>
> `settings.json` keys are rejectable individually (see Step 4 below), so
> retiring one setting no longer means rejecting the whole file.

## Step 4 — Backup, then apply through the propagator seam

Always back up before touching local state so the user has a rollback path.

```bash
BACKUP_PATH=$(py "$ENGINE" backup)
echo "Backup saved: $BACKUP_PATH"

# Applies config (SnapshotPropagator: consolidated snapshot → CLAUDE.md/memory/rules/
# settings) AND skill/agent bundles (ContentBundlePropagator). Prints per-propagator
# {applied, skipped, conflicts}. Replaces the old standalone `import`.
APPLY=$(py "$ENGINE" propagate-apply "$REPO")
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
py "$ENGINE" resolve-bundle "$REPO" "<kind>" "<name>" "<winner>"
```

**Resolve bundle deletions (if any).** For each entry in `content-bundle.deletions` —
a skill/agent the network retired that this machine still has — ask the user with
**AskUserQuestion** ("Skill/agent `<name>` was deleted on `<machine_id>` at
`<deleted_at>` — remove it here, or keep it?"), then apply their choice:

```bash
# decision is "remove" (delete this machine's copy) or "keep" (retain it; the next
# export re-adds it for everyone)
py "$ENGINE" resolve-deletion "$REPO" "<kind>" "<name>" "<decision>"
```

**Reject content you never want (if any).** For any proposal the user declines,
offer a third answer beyond apply/skip: reject it durably. Ask with
**AskUserQuestion** whether the rejection is for this machine only or for the
whole network, then record it:

Phase 1 kinds address the snapshot; phase 2 adds the rest of what syncs:

```bash
# scope is `local` (this machine only) or `network` (tombstone for everyone)
# a section of a markdown file, or a whole file
py "$ENGINE" reject "$REPO" snapshot-section CLAUDE.md --section "## Memory protocol" --scope network
py "$ENGINE" reject "$REPO" snapshot-file rules/unwanted.md --scope local

# one key inside settings.json -- --key is repeatable and gives the path in order
py "$ENGINE" reject "$REPO" settings-key - --key permissions --key defaultMode

# a marketplace plugin, by the id plugins-plan uses
py "$ENGINE" reject "$REPO" plugin open-memory@open-memory

# one hook registration -- a script basename is only unique within an
# event and matcher, so both are required
py "$ENGINE" reject "$REPO" hook-registration enforce_gates.py \
  --event PreToolUse --matcher Bash
```

A hook rejection records the **identity tier** it resolved to. Tier 2 (event +
matcher + script name) survives an interpreter change or a relocation, which is
what stops a reinstalled hook coming back under a new identity. When two
registrations share an event, a matcher and a script name, resolution falls to
tier 3 — an exact match on the command — because at that point you are rejecting
one specific copy.

> **Rejecting a hook stops it being wired; it does not unregister it.**
> config-sync only ever edits its own marked entries, so a registration already
> in `settings.json` stays until `hooks-prune` removes it. The two compose:
> `reject` stops it coming back, `hooks-prune` takes out what is already there.

> **Where a rejection is checked depends on what it writes.** Consolidate
> (Step 3) writes the shared consolidated snapshot, so it uses a network-only
> policy — a local veto leaking in there would impose one machine's private
> taste on every other machine. Plugin convergence and hook wiring (Step 4b,
> Step 4c) write only this machine's local state, so they use the composite
> policy: your local rejections and the network's, both checked. `settings-key`
> is filtered at both points, because it is written in both places.

A rejection is timestamped: content re-added *later* than the rejection is
proposed again as fresh intent. Review or undo with `py "$ENGINE" rejections "$REPO"`
and `py "$ENGINE" unreject "$REPO" <id>`.

## Step 4b — Converge marketplace plugins (plan → consent → apply)

Skills/agents flow through `propagate-apply` (above); config through the snapshot
propagator. **Plugins** converge here from the desired-state manifest. First compute
the plan (pure — nothing is mutated):

```bash
PLAN=$(py "$ENGINE" plugins-plan "$REPO")
printf '%s\n' "$PLAN"
```

Parse `$PLAN`. If `.actions` is empty, tell the user "plugins already up to date" and
continue. Otherwise render the actions (each has `verb` + `target`) and ask with
**AskUserQuestion**: "Apply these plugin changes? — refresh N marketplace(s),
install M, update K plugin(s)." Also surface any `.skipped` entries (e.g. a
marketplace whose source is unknown).

If the user declines, stop here — nothing has been changed. If they accept, execute:

```bash
APPLIED_PLUGINS=$(py "$ENGINE" plugins-apply "$REPO")
printf '%s\n' "$APPLIED_PLUGINS"
```

Parse `.outcomes` and report which plugins were installed/updated; surface any
`ok:false` entries with their `message`. Remind the user to restart Claude to
activate newly installed plugins.

Finally, install any **legacy** shared skills/rules/agents from older machines
(never overwriting local copies):

```bash
SHARED_RESULT=$(py "$ENGINE" apply-shared "$REPO")
printf '%s\n' "$SHARED_RESULT"
```

## Step 4c — Wire declared hooks

After the plugin convergence step, provision any repo-shipped hooks this machine
is missing:

1. Run `py "$ENGINE" hooks-plan`. It scans the declared roots
   (`CONFIG_SYNC_ROOT_*`) for `hooks/hooks.json` files and lists the hook
   registrations missing from `~/.claude/settings.json`.
2. If `actions` is empty, say so and move on.
3. Otherwise show the user each action and ask once for confirmation — this is
   the single consent gate. An action's `verb` says what will happen:
   - `register` — a new hook, appended.
   - `update` — a hook config-sync already wired whose declaration moved (a new
     interpreter, a relocated script). It is rewritten **in place**, at the
     `location` shown, rather than appended alongside its predecessor.
4. On yes, run `py "$ENGINE" hooks-apply`. It writes each registration in
   portable `${TOKEN}` form, tagged `# config-sync:<id>` so it is never confused
   with a hand-added hook. Re-running is a safe no-op.

Never run `hooks-apply` without the user's confirmation.

Hook identity keys on the **script**, not the whole command string, so changing
the interpreter in front of it resolves to the same registration. Ids marked by
older versions were hashed over the full command; they are re-found by script
name and re-marked in place (one `update` per hook, then quiet forever).

A declaration whose script is **not on this machine** is skipped rather than
wired — otherwise apply would register it, prune would delete it as a dead
target, and the next apply would register it again. The skip reason says so. If
you see one, the repo is probably not checked out where its root points.

Two limits worth knowing:
- Editing a hook's **event or matcher** still orphans its previous registration —
  both are inside the identity. Pin an `"id"` in `hooks.json` to survive that.
- Two hooks declared for the same event and matcher that resolve to the same
  script are **both skipped** as ambiguous, with a message saying so. Give each
  an `"id"` to tell them apart.

## Step 4d — Check the wired hooks are still healthy

Wiring only ever adds. Over time a target moves or a second copy of the same
guard gets wired from another install location, and once a path disappears the
dead hook prints an error on every tool call in every project.

1. Run `py "$ENGINE" hooks-doctor` — read-only, never writes. It reports every
   hook in `~/.claude/settings.json`, not just config-sync's.

   **Definitive** (a deletion may be justified — the evidence does not depend on
   this machine's environment):
   - `missing-target` — an **absolute** path in the command is not on disk.
   - `duplicate-command` — another entry runs the same argv, for the same event
     and matcher, with absolute paths resolved.

   **Advisory** (reported, never acted on):
   - `duplicate-script` — a same-named script from a *different* install
     location. Two files with one basename may both be wanted.
   - `missing-on-path` — a bare program name this process could not find. The
     hook runs in a different shell, with a different PATH.
   - `unresolvable` — a relative path or a glob. Hooks run with cwd set to the
     project directory; the doctor cannot know it.
   - `opaque` — a shell fragment, or any command containing `$`. Counted as
     `unchecked` in the summary, never reported as broken.

2. Gate on `summary.prunable_by_default`, **not** `summary.repairable` —
   `repairable` counts hand-added entries that the default run will skip. If it
   is 0, say so and move on.
3. Otherwise show the findings and ask once. On yes, run
   `py "$ENGINE" hooks-prune`. It removes only entries with a **definitive**
   finding, and only ones config-sync wired. It writes
   `~/.claude/settings.json.pre-prune-<timestamp>` before its first deletion and
   returns the path as `backup` — tell the user where it is.
4. Only if the user explicitly asks to clean up hand-added hooks too, run
   `py "$ENGINE" hooks-prune --include-unmanaged`. Confirm separately: this
   deletes hooks config-sync did not create.

Never run `hooks-prune` without the user's confirmation. Advisory findings are
never pruned automatically — report them and let the user decide.

If an entry reports `ok: false`, settings.json changed between the diagnosis and
the write; nothing was removed for it. Re-run `hooks-doctor`.

## Step 4e — Answer other machines' rejections

`propagate-apply` reports a `rejection_removals` list under the `snapshot`
propagator: the content a rejection kept off this machine. Two things reach it —
content the consolidated snapshot still carried, which this apply filtered out,
and content `consolidate` withheld from **this machine's own snapshot** before it
ever reached the consolidated one. The second kind travels in the consolidated
snapshot's `withheld` key, attributed to the machine that held it, so only that
machine is asked — and **not even that machine, if it is the one that recorded
the rejection**. A rejection withholds and never deletes, so the rejecting
machine is still holding the content it just rejected; asking its own operator
to reconsider on their very next apply would be noise. If you are on the machine
that ran `reject` and expected a prompt about your own network rejection, that
is why there is none: `unreject` is the route back. Each entry is the full
ledger record, e.g.

```json
{
  "id": "3f1c9a0b7d24",
  "kind": "snapshot-section",
  "address": "{\"file\": \"CLAUDE.md\", \"heading\": \"## Memory protocol\", \"occurrence\": 0}",
  "scope": "network",
  "rejected_at": "2026-08-03T09:00:00+00:00",
  "machine_id": "Mac.fritz.box",
  "reason": "superseded by the mente skill",
  "tier": "",
  "revives": null
}
```

Entries with `"scope": "local"` are **this** machine's own vetoes — mention them
in the Step 7 summary, do not prompt. For each `"scope": "network"` entry, ask
with **AskUserQuestion** ("`<address>` was rejected on `<machine_id>` at
`<rejected_at>` — remove it here, or keep it?") and apply the answer using that
entry's `id`:

```bash
py "$ENGINE" resolve-rejection "$REPO" <id> remove   # agree: withhold it here
py "$ENGINE" resolve-rejection "$REPO" <id> keep     # overrule: it returns for everyone
```

`remove` records a **local** rejection for the same address, so this machine
stops writing that content from the next apply onward. Where the content was
still in the consolidated snapshot, it does not erase the copy already on disk in
this run — the next sync's apply rewrites the file without it, and only the sync
after that exports a copy that no longer carries it.

Where `consolidate` withheld it upstream, what is already on disk depends on the
kind, exactly as the callout below sets out. For a `snapshot-section` or a
`settings-key` the container file still reaches apply, so `CLAUDE.md` or
`settings.json` has already been rewritten without the unit and `remove` is only
the record that keeps it gone if another machine later revives it. For a
`snapshot-file` the consolidated snapshot has **no key** for the file at all, so
apply wrote nothing and this machine's copy is untouched on disk — `remove` is
what stops the next export re-publishing it, and the file itself stays until you
delete it yourself. A rejection withholds; it never deletes.

`keep` does not edit the rejecting machine's file. It records this machine's own
newer revival, which wins on timestamp — so one machine can always overrule the
network without a cross-machine write. It is not instant, and it does not wait:
see the window below.

> **A network rejection now converges without an answer here.** Phase 3's
> per-content provenance stamps each unit's own `changed_at` from a hash
> against that machine's last snapshot, not the export's wall clock (see the
> Step 3 note) — so a machine that still holds the content but has not edited
> it stops re-adding it on its own. `resolve-rejection` keeps a narrower
> meaning: it is for a machine that actively disagrees. `remove` records that
> agreement here; `keep` still lets one machine overrule the network — but
> only inside the window below.
>
> **Answer before this machine's next export, and re-run `consolidate`.** What
> `keep` revives from is this machine's last export,
> `machines/<machine-id>.json`, which by this point is the only copy of the
> content the network has. Answering only writes the revival record; the
> **next** `consolidate` is what puts the content back into the consolidated
> snapshot, and the apply after that puts it back on disk. So after a `keep`,
> re-run `py "$ENGINE" consolidate "$REPO"` and
> `py "$ENGINE" propagate-apply "$REPO"` before going on to Step 5. If this
> machine exports again first, it overwrites `machines/<machine-id>.json` with
> its post-apply state, the last copy is gone, and neither `keep` nor
> `unreject` can bring it back — only git history can.
>
> **Whether the content is still on this machine's disk depends on the kind.**
> A `snapshot-file` rejection withholds the whole file, so the consolidated
> snapshot has no key for it, apply writes nothing, and this machine's copy
> survives untouched (a rejection withholds, it never deletes) — so `keep` and
> `unreject` keep a live local source indefinitely. A `snapshot-section` or
> `settings-key` rejection leaves its container file in the snapshot: apply
> rewrites `CLAUDE.md` or `settings.json` **without** the rejected unit, so
> that content is already off this machine's disk by the time this prompt
> appears. That is why the window above is what matters for sections and keys,
> and why it does not bite for whole files.
>
> Editing content is the intended escape hatch — an operator who wants
> rejected content back edits it, or runs `unreject`. A `snapshot-file`
> rejection's unit of intent is the whole file, so editing any part of it
> re-adds the whole file; editing one section never re-adds a *different*
> rejected section in the same file, since each section is hashed on its own.
>
> A machine on an engine older than phase 3 has no `provenance` map to
> compare against, so it keeps the old wall-clock behaviour until it
> upgrades. No flag day.

## Step 5 — Commit the updated consolidated snapshot and rejections, then push

This is the commit that carries `rejections/`. `reject` and `resolve-rejection
keep` run at Step 4 — *after* Step 1 has already committed — so Step 1's staging
can only ever pick up a ledger left behind by an earlier run. Without this one, a
`--scope network` rejection stays an uncommitted working-tree change forever and
never reaches another machine.

```bash
cd "$REPO"
git add consolidated/
if [ -d rejections ]; then git add rejections/; fi
git diff --cached --quiet && echo "consolidated snapshot and rejections unchanged" || \
  git commit -m "merge: consolidated + rejections at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

git push origin main 2>&1
```

## Step 6 — Write sync log entry and update config

```bash
# Summarise what changed for the log (sum applied entries across both propagators)
APPLIED=$(printf '%s\n' "$APPLY" | py -c "import json,sys; d=json.load(sys.stdin); print(sum(len(section.get('applied',[])) for section in d.values()))" 2>/dev/null || echo "?")
SHARED_IN=$(printf '%s\n' "$SHARED_RESULT" | py -c "import json,sys; print(len(json.load(sys.stdin)['installed']))" 2>/dev/null || echo "0")

py "$ENGINE" log-sync "$REPO" "sync" "$APPLIED file(s) updated, $SHARED_IN shared artifact(s) installed"

# Persist the log entry. log-sync writes meta/sync-log.json but does not commit it,
# so without this the sync log never reaches the remote — it just accumulates as an
# uncommitted local change. Commit + push it now (a no-op when nothing changed).
cd "$REPO"
git add meta/
git diff --cached --quiet && echo "sync log unchanged" || \
  { git commit -m "log: sync entry for $MACHINE_ID at $(date -u +%Y-%m-%dT%H:%M:%SZ)"; git push origin main 2>&1; }

# Update last_sync timestamp in local config
py - <<EOF
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
  Rejected : <N> item(s) rejected (or "none")
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

# Interpreter choice lives in bin/mente-python, not here: uv first (honouring
# the operator's own pin), a new-enough system interpreter second, and a
# diagnosis rather than a SyntaxError if neither exists. Keeping it in one file
# is why that order can change without editing every skill that runs Python.
# A function, not a variable — zsh does not word-split an unquoted expansion,
# so a multi-word PY="..." would be looked up as one long command name.
LAUNCHER="$(dirname "$(dirname "$ENGINE")")/bin/mente-python"
py() { sh "$LAUNCHER" "$@"; }

# With no pin anywhere, uv picks whatever it can find, and "whatever it can
# find" differs per machine — the drift this plugin exists to prevent. uv walks
# up from $PWD for a .python-version before falling back to the global pin, so
# this looks in the same order rather than only at the current directory.
pinned() {
  directory=$PWD
  while [ "$directory" != "/" ]; do
    [ -f "$directory/.python-version" ] && return 0
    directory=$(dirname "$directory")
  done
  [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/uv/.python-version" ]
}
# Only worth saying when uv is the thing doing the choosing. With uv absent the
# launcher has already printed the one useful instruction, and this nudge would
# contradict it — then recommend `uv python pin`, a command that machine cannot
# run.
if command -v uv >/dev/null 2>&1 && ! pinned; then
  echo "No Python pin found — uv is choosing an interpreter for you. Pin one:"
  echo "  uv python pin --global $(py -c 'import sys; print(sys.version.split()[0])')"
fi
REPO="$HOME/.claude/config-sync-repo"

if [ ! -d "$REPO" ]; then
  echo "config sync is not set up yet. Run /config-sync-setup first."
  exit 0
fi

# Local inventory
py "$ENGINE" status

# Network: list all machines in the repo
if [ -d "$REPO/machines" ]; then
  echo ""
  echo "── Network machines ────────────────────────────────"
  for snap in "$REPO/machines/"*.json; do
    py - "$snap" <<'EOF'
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
  py - "$REPO" <<'EOF'
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
  py - "$REPO/meta/sync-log.json" <<'EOF'
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
py "$ENGINE" propagate-apply "$REPO"
```

Then continue to Step 5 (commit and push the resolved consolidated snapshot).
