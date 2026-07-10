# Bundle deletion propagation — design

**Date:** 2026-07-08
**Project:** mente-apex-plugin — config-sync engine
**Scope:** skill/agent **bundles** only (not snapshot config)
**Semantics:** broadcast + consent, via timestamped tombstones

---

## 1. Problem

Config-sync propagates `~/.claude/skills` and `~/.claude/agents` as content-hashed
bundles (`ContentBundlePropagator`). Today deletions do not propagate, and worse,
a deleted bundle is **resurrected**:

- **Export** (`ContentBundlePropagator.export`) writes/updates a repo bundle for
  every skill that exists locally, but never prunes a bundle when the local skill
  is gone, and keeps no record of what this machine exported last time — so it
  cannot even detect a deletion. (Confirmed: after deleting `~/.claude/skills/gof`,
  `propagate-export` left `bundles/skills/gof` stale in the repo.)
- **Apply** (`ContentBundlePropagator.apply`) installs *any* repo bundle missing
  locally — so a stale bundle re-creates the skill on the next sync.

The result is the limitation the skill documents ("Deletions don't propagate…
resurrected from another machine's snapshot"). Retiring a skill everywhere
currently requires manually `git rm`-ing the bundle on the shared repo.

**Goal:** deleting a skill/agent on one machine removes it from the others — after
a per-machine consent prompt — without a mistaken delete silently wiping it
everywhere, and without a race that resurrects it.

**Non-goals (YAGNI):** propagating deletions *inside* snapshot config
(CLAUDE.md / `memory/` / `rules/`) — that needs section-level tombstones and stays
union-only for now. Auto-pruning old tombstones. A "keep it here only" per-machine
suppression state.

## 2. How DIP shaped this

The new responsibility — *tracking what was deleted* — is a new abstraction,
`BundleDeletionLedger`, **injected into `ContentBundlePropagator` through the
constructor** (exactly like the existing `BundleExportFilter`). The propagator
depends on the ledger's interface, never on where tombstones/index live; tests
substitute a ledger rooted at `tmp_path`. The destructive removal is separated
from the decision to remove: the propagator *proposes* deletions (data in
`ApplyResult`), and a distinct consent-gated command performs the removal — policy
(consent) decoupled from mechanism (rmtree), mirroring the existing
plan→consent→apply seam for plugins and the surface→resolve seam for bundle
conflicts.

## 3. New unit — `BundleDeletionLedger`

Lives in `config_sync_propagators.py`. Rooted at `repo_dir`. All state is
git-tracked and **per-file** so it converges without merge conflicts (the pattern
`machines/<id>.json` already uses).

State:
- **Per-machine export index** — `bundles/.index/<machine_id>.json`:
  `{"machine_id", "updated_at", "bundles": ["skill/foo", "agent/bar", …]}` — the
  set of `kind/name` this machine had at its last export. Enables deletion
  *detection*.
- **Tombstones** — `bundles/.tombstones/<subdir>/<name>.json` (subdir =
  `skills`/`agents`): `{"kind", "name", "deleted_at", "machine_id"}`, one file per
  retired bundle.

Interface (all take explicit args; no globals):
```
previously_exported(machine_id) -> set[str]        # read index (empty if none)
record_export(machine_id, current_set) -> None     # write index
tombstone(kind, name, machine_id, when) -> None     # write tombstone file
clear_tombstone(kind, name) -> None                 # remove tombstone file (re-add)
tombstones() -> list[Tombstone]                     # all tombstones
tombstone_for(kind, name) -> Tombstone | None
is_deleted(kind, name, bundle_exported_at) -> bool  # tombstone.deleted_at > exported_at
```

`Tombstone` is a small frozen dataclass. Timestamps are ISO-8601 UTC strings,
compared lexicographically (ISO-8601 sorts correctly), matching the snapshot
consolidation's `timestamp` handling.

`bundles/.index/` and `bundles/.tombstones/` start with a dot and are **not**
under `bundles/skills` or `bundles/agents`, so the existing apply/export iterators
(`bundles/<subdir>/*`) never mistake them for bundles.

## 4. Export detects & records deletions

`ContentBundlePropagator.export(context)` — the new steps wrap the existing
hash-gated write loop:

1. `current = { f"{kind}/{name}" for kind, entry in self._sources(context) }`.
2. `previous = ledger.previously_exported(machine_id)`.
3. `deleted = previous - current`. For each `kind/name` in `deleted`:
   - `ledger.tombstone(kind, name, machine_id, now)`;
   - remove the repo bundle dir `bundles/<subdir>/<name>` if present
     (`shutil.rmtree`), so the git tree reflects the removal.
4. For each `kind/name` in `current` that has a tombstone with
   `deleted_at < now`: `ledger.clear_tombstone(kind, name)` — this export is a
   deliberate re-add and supersedes the older tombstone.
5. `ledger.record_export(machine_id, current)`.
6. Existing behavior unchanged: write/refresh each changed bundle (hash-gated),
   append to `result.written` / `result.skipped`.

`ExportResult` gains a `tombstoned` list (the `kind/name`s newly tombstoned) so
the sync summary can report them.

Edge: a machine with **no prior index** (first sync ever) has `previous = {}`, so
`deleted` is empty — it tombstones nothing (no false deletions), and step 5
records its first index.

## 5. Apply proposes deletions; a consent-gated command removes them

`ApplyResult` gains a `deletions` list of `BundleDeletion(kind, name, machine_id,
deleted_at)` — *proposed*, not performed.

`ContentBundlePropagator.apply(context)`:
- Existing per-bundle loop, with one guard added: before installing a repo bundle
  that is **missing locally**, if `ledger.is_deleted(kind, name, manifest.exported_at)`
  is true, do **not** install (kills resurrection) and skip it.
- New pass over `ledger.tombstones()`: for each tombstone whose local skill/agent
  **still exists** and which out-times any live repo bundle for that name
  (`is_deleted(..., bundle_exported_at_or_empty)`), append a `BundleDeletion` to
  `result.deletions`. Nothing is removed here.

New module-level entry point + CLI command, mirroring `resolve_bundle` /
`resolve-bundle`:
```
resolve_deletion(context, kind, name, decision)   # decision ∈ {"remove","keep"}
```
- `remove`: `shutil.rmtree` the local `~/.claude/<subdir>/<name>` (guarded by
  `_is_within`). The repo bundle is already gone; the tombstone remains.
- `keep`: no-op locally. Because the machine still has the skill, its next
  `export` sees it in `current`, re-adds the bundle, and clears the tombstone —
  genuine disagreement resolves as "most recent action wins."

CLI: add `"resolve-deletion": (cmd_resolve_deletion, 4)` to the dispatch table,
with `cmd_resolve_deletion(repo_path, kind, name, decision)` — mirroring the
existing `"resolve-bundle": (cmd_resolve_bundle, 4)` /
`cmd_resolve_bundle(repo_path, kind, name, winner)` exactly (the dispatcher calls
`fn(*args[1:])` with the declared arg count).

## 6. Skill workflow + documentation

`skills/config-sync/SKILL.md`:
- **Step 1** summary line: if `propagate-export` reports `tombstoned` entries, note
  "retired N skill/agent(s): …".
- **Step 4**, after the existing bundle-conflict resolution: parse
  `content-bundle.deletions`. For each, ask with `AskUserQuestion` — *"Skill/agent
  `<name>` was deleted on `<machine_id>` at `<deleted_at>` — remove it here, or
  keep it?"* — then run `python3 "$ENGINE" resolve-deletion "$REPO" <kind> <name>
  <remove|keep>`.
- Update the **"Deletions don't propagate"** callout: skill/agent *bundles* now
  propagate deletions (with consent); snapshot **config** (CLAUDE.md/memory/rules)
  is still union-only and unchanged.
- **Step 7** summary: add a "Retired: N bundle(s)" line when applicable.

## 7. Testing

TDD in `tests/`, following `tests/test_propagators.py` conventions (`SyncContext`
over `tmp_path`; helper `_write_skill`). New tests:

- **Ledger unit:** `previously_exported` empty when no index; `record_export` then
  `previously_exported` round-trips; `tombstone` / `tombstone_for` / `clear_tombstone`;
  `is_deleted` true when `deleted_at > exported_at`, false otherwise (incl. equal).
- **Export detection:** export a skill (index recorded) → delete it locally →
  re-export → tombstone written, repo bundle pruned, `result.tombstoned` lists it.
- **Re-add supersedes:** tombstone exists → recreate the skill locally → export →
  tombstone cleared, bundle re-written.
- **Apply anti-resurrection:** repo has a bundle + a newer tombstone, skill absent
  locally → apply does **not** install it, no `applied` entry.
- **Apply proposes deletion:** repo tombstone out-times a live bundle, skill
  present locally → `result.deletions` contains it; nothing removed.
- **resolve-deletion:** `remove` deletes the local dir (and refuses a path escaping
  `~/.claude`); `keep` leaves it in place.
- **First-sync safety:** export with no prior index tombstones nothing.
- **CLI:** `test_propagate_cli` / a new case covers `resolve-deletion` dispatch and
  argument handling.

## 8. Delivery

Branch `fix/bundle-deletion-propagation`. Implement test-first, full suite green
after each unit. Bump the plugin version (0.10.0 → 0.11.0, minor: new
capability) across `plugin.json` / `pyproject.toml` / `marketplace.json`; note the
new behavior in README's config-sync section. Offer a commit + PR at the end per
`docs/git-convention.md` — never auto-publish.

## 9. Open questions carried to planning

- Exact filename escaping for tombstones if a bundle name ever contained a path
  separator — bundle names are single directory names today (no separators), so a
  flat `<name>.json` is safe; assert/validate the name has no `/` when writing.
- Whether `ExportResult.tombstoned` and `ApplyResult.deletions` should also flow
  into the `meta/sync-log.json` entry (leaning yes — one extra field — so retired
  bundles are auditable in the sync history).
