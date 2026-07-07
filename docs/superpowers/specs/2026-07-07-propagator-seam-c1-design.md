# Propagator Seam — Phase C1 Design

**Date:** 2026-07-07
**Status:** Approved (brainstorm) — pending spec review
**Closes (C1):** PS4 #25 (root cause), PS2 #23 (multi-file skill assets dropped — *data loss*), PS3 #24 (local plugin/skill updates frozen), D8 #16 (bloat + formatting churn), SK1 #26 (export lives in a SKILL heredoc)
**Deferred to C2:** PS1 #22 (marketplace refresh) — `MarketplacePropagator`, additive.

---

## Context

config-sync has two propagation channels and locally-authored content falls through both:

- **Snapshot channel** (every sync): `CLAUDE.md`, `memory/`, `rules/`, `skills/`, `agents/`, `settings.json` — but `_collect_dir` filters to `.md/.json/.txt`. A skill with `scripts/engine.py` + `fonts.css` exports with **only** `SKILL.md` → arrives as a non-working shell (**PS2, data loss**).
- **Shared channel** (`shared/`, manual `/config-sync-manage share`): all files, but first-time-only. Export skips if `shared/plugins/<key>` exists and apply skips if the plugin is already installed → a rebuilt local skill/plugin **never re-propagates** (**PS3, freeze**).

Root cause (**PS4**): two different propagation responsibilities are conflated behind one ad-hoc "copy the live cache" strategy, implemented inline in a `SKILL.md` heredoc (**SK1** — untestable, re-parsed as shell every run).

**Outcome:** one `Propagator` seam with substitutable implementations. C1 delivers the seam plus the two propagators that fix the data-loss/freeze bugs; the marketplace channel is a later, additive propagator.

---

## Decisions (from brainstorm)

1. **Decomposition:** C1 = seam + `SnapshotPropagator` + `ContentBundlePropagator`. C2 = `MarketplacePropagator` (own spec).
2. **Skills & agents are atomic, hash-gated bundles** — all files travel; `SKILL.md` no longer section-merges (a skill is a program, not a prose doc). `SnapshotPropagator` keeps only mergeable config.
3. **Conflicts prompt** (not silent recency-wins): `apply()` detects a divergent bundle, leaves the local copy untouched, and returns it as data; the SKILL drives `AskUserQuestion`; a thin `resolve-bundle` command performs the choice — mirroring the existing `CLAUDE.md` merge-conflict UX.
4. **Sharing:** all local `~/.claude/skills/` + `~/.claude/agents/` auto-propagate (completing today's partial behavior). `share` becomes plugin-only until C2.
5. **Deletions:** unchanged — union-only (accepted trade-off). Bundles add/update, never delete.
6. **Module structure:** keep `config_sync.py` as the CLI entry; the seam lives in a sibling `scripts/config_sync_propagators.py`.

---

## Architecture (DIP)

The sync cycle depends only on the `Propagator` abstraction. Implementations are injected as a list; paths are injected via `SyncContext` (no module globals); hashing and conflict detection are encapsulated inside `ContentBundlePropagator`. Adding `MarketplacePropagator` in C2 is pure open/closed — append to the factory, edit no tested logic.

```python
# scripts/config_sync_propagators.py

@dataclass(frozen=True)
class SyncContext:
    claude_dir: Path      # injected — the local ~/.claude
    repo_dir: Path        # injected — the config-sync repo

@dataclass
class BundleConflict:
    kind: str             # "skill" | "agent"
    name: str
    local_hash: str
    repo_hash: str
    local_exported_at: str
    repo_exported_at: str

@dataclass
class ExportResult:
    propagator: str
    written: list[str]
    skipped: list[str]

@dataclass
class ApplyResult:
    propagator: str
    applied: list[str]
    skipped: list[str]
    conflicts: list[BundleConflict]

class Propagator(Protocol):
    name: str
    def export(self, context: SyncContext) -> ExportResult: ...
    def apply(self,  context: SyncContext) -> ApplyResult:  ...

def default_propagators() -> list[Propagator]:
    return [SnapshotPropagator(), ContentBundlePropagator()]
    # C2 appends MarketplacePropagator()
```

`run_export(context, propagators)` / `run_apply(context, propagators)` iterate the injected list and aggregate results. The list is a parameter — tests inject a single fake propagator or a `ContentBundlePropagator` alone.

### SnapshotPropagator
Wraps the existing snapshot logic, **scoped to mergeable config only**:
- **Collection set:** `CLAUDE.md`, `memory/`, `rules/`, `settings.json`, `keybindings.json`. `skills`/`agents` are **removed** from its scope.
- **export:** writes the machine snapshot to `machines/<machine_id>.json` (reuses `cmd_export`'s collection minus skills/agents, plus `_clean_settings`).
- **apply:** reads `consolidated/snapshot.json` and writes those config files locally (reuses `cmd_import`'s logic incl. `_merge_import_settings` and the `_safe_dest` guard); **defensively skips** any `skills/`·`agents/` keys still present in legacy snapshots (graceful migration — see below).
- Snapshot **merging** stays in the separate `consolidate` step (unchanged) — merging machine snapshots is distinct from applying them, and remains its own SKILL step.

### ContentBundlePropagator
Owns `~/.claude/skills/*` and `~/.claude/agents/*` as atomic bundles.

- **Bundle:** one skill/agent dir → `bundles/<kind>/<name>/` in the repo, containing every file plus `bundle-manifest.json = {name, kind, content_hash, exported_at, machine_id}`.
- **content_hash:** `sha256` over sorted `(relative_path, file_bytes)` for all files in the dir (manifest excluded).
- **export (fixes PS3, D8):** for each local bundle, compute hash. If repo bundle hash == local hash → skip (no churn). Else → write bundle + manifest. Gated on **hash, not presence**.
- **apply (fixes PS2):** for each repo bundle: local absent → install all files. local hash == repo hash → skip. local hash != repo hash → **conflict**: leave local untouched, append a `BundleConflict`. Every file travels (no `.md/.json/.txt` filter).
- **safety:** all destination writes go through the existing `_is_within(dest, claude_dir)` guard (C2 #10 defense reused).

### Conflict resolution (prompt)
`resolve_bundle(context, kind, name, winner)` where `winner ∈ {"local","repo"}`:
- `"repo"` → overwrite the local skill/agent dir from the repo bundle (Step-4 `backup` already preserves the old copy).
- `"local"` → re-export the local dir into the repo bundle (local wins; propagates next).

The SKILL surfaces each `BundleConflict` via `AskUserQuestion` and calls `resolve-bundle` with the choice.

---

## Repo layout

```
config-sync-repo/
  machines/*.json             # SnapshotPropagator (skills/agents keys ignored on apply)
  consolidated/snapshot.json  # "
  bundles/
    skills/<name>/…  + bundle-manifest.json
    agents/<name>/…  + bundle-manifest.json
  shared/…                    # legacy for skills/agents (read-only fallback); plugins stay until C2
  meta/sync-log.json
```

---

## Command surface (`config_sync.py` → delegates to the propagators module)

| Command | Behavior |
|---|---|
| `propagate-export <repo>` | Build `SyncContext`, run each propagator's `export`; print aggregated JSON. **Replaces** the standalone `export > machines/…` line **and** the plugin-export heredoc (SK1). |
| `propagate-apply <repo>` | Run each propagator's `apply`; print `{applied, skipped, conflicts}`. **Replaces** the standalone `import` (Step 4) and the skills/agents half of `apply-shared` (Step 4b). |
| `resolve-bundle <repo> <kind> <name> <local\|repo>` | Perform the user's conflict choice. |

Existing `export` / `import` / `consolidate` remain as building blocks and back-compat CLI (the propagators reuse their logic). `consolidate` still runs as its own SKILL step (Step 3) between push and apply. New commands are thin wrappers that inject the context and delegate — no file manipulation in `SKILL.md` (fixes SK1).

---

## SKILL orchestration changes (`skills/config-sync/SKILL.md`)

- **Step 1 (export):** after `reconcile` + snapshot `export`, call `python3 "$ENGINE" propagate-export "$REPO"` (replaces the plugin-export heredoc entirely — SK1).
- **Step 4b (apply shared):** replace `apply-shared` skills/agents handling with `propagate-apply "$REPO"`. Parse `conflicts`; for each, `AskUserQuestion` (keep local / take network) → `resolve-bundle`. Report applied bundles in the summary.
- **`/config-sync-manage share`:** note that skills/agents now auto-propagate; `share` is plugin-only (until C2).
- Bump `config-sync` skill version (0.5.0 → 0.6.0).

---

## Migration — graceful & additive (no repo rewrite)

No `machines/*.json` rewrite and no risky repo surgery:
1. `SnapshotPropagator` stops collecting `skills`/`agents` and **defensively skips** those keys on apply, so legacy skill-text in old snapshots goes inert.
2. `ContentBundlePropagator` re-materializes each machine's local skills/agents as bundles on the next sync (they exist locally on every machine).
3. `shared/skills`·`shared/agents` become a read-only legacy fallback — no longer written.
4. **Apply order: Snapshot → then bundles**, so a bundle always wins over any stale snapshot text for the same path.

---

## Concurrency note

The apply-time `BundleConflict` prompt handles the common case (one machine ahead/behind on a skill). The rarer case — two machines edit the *same* skill divergently **between** syncs — can surface as a **repo-level git conflict** in `bundles/<kind>/<name>/…` during Step 2 `git pull`, because the hash gate only suppresses re-export when local matches the repo. That's the same fragility any shared file has today; it's resolved like other repo conflicts (keep one side, re-run the skill). A full distributed bundle-merge protocol is explicitly out of scope (YAGNI) — the hash gate + apply-time prompt cover normal use.

## Testing (`tests/test_propagators.py`, injected `SyncContext` — no global monkeypatching)

- Multi-file skill (`SKILL.md` + `scripts/x.py` + `fonts.css`) round-trips with **all** files present (PS2).
- Rebuilt skill (content changed → new hash) **re-exports**; unchanged skill is **skipped** (PS3, D8).
- `apply` on a divergent bundle returns a `BundleConflict` and does **not** overwrite the local dir.
- `resolve-bundle repo` overwrites local from repo; `resolve-bundle local` re-exports local into the repo.
- `SnapshotPropagator.apply` ignores `skills/`·`agents/` keys in a legacy snapshot.
- Destination-escape attempt in a bundle name/path is rejected via `_is_within`.
- `run_apply` aggregates results across an injected list of propagators (fake + real).

---

## Out of scope (C1)

- `MarketplacePropagator` / marketplace refresh (PS1 #22) — C2.
- Deletion tombstones — union-only stays.
- Local plugin bundles — reuse `ContentBundlePropagator` in C2 alongside the marketplace channel.
- No package restructure; `config_sync.py` stays the entry point.
