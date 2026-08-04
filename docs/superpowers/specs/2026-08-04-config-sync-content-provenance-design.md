# Per-content provenance — closing the rejection ledger's bounded convergence (phase 3)

**Status:** design approved, ready for an implementation plan.
**Predecessors:** `2026-08-03-config-sync-rejection-ledger-design.md` (phase 1),
`2026-08-03-rejection-ledger-phase-2.md` (phase 2, merged as `e778b6e`).

## 1. The defect

`TimestampedRejectionRule.suppresses` asks whether incoming content is strictly newer
than the rejection that targets it. The answer it gets is wrong, because the timestamp it
compares against is the wrong clock.

`SnapshotPropagator.export` stamps one `datetime.now(UTC)` on the whole machine snapshot
(`scripts/config_sync_propagators.py:873`) — the time the *export ran*, not the time the
*content changed*. `cmd_consolidate` then passes that stamp as `source_timestamp` for
every unit in the snapshot.

So a machine that still holds rejected content and has not touched it re-exports that
content under a fresh wall-clock stamp, strictly newer than the rejection. The rule reads
it as a deliberate re-add and the content resurrects. Phase 1 states the consequence
plainly:

> an unchanged re-export is, to this engine, indistinguishable from a deliberate re-add

The operator's only recourse today is to answer `resolve-rejection … remove` on every
machine that still carries the content. That is the "bounded convergence" phase 1
documented and phase 2 deliberately did not address.

## 2. Goal

Make an unchanged re-export distinguishable from a deliberate re-add, so a network
rejection converges across the fleet without per-machine intervention.

**Success:** machine A rejects content; machine B still holds it unchanged; B exports;
consolidate runs; the content stays withheld. Today that sequence resurrects it.

## 3. Scope

Only three of the five rejectable kinds can resurrect:

| Kind | Filter point | `source_timestamp` today | Can resurrect? |
|---|---|---|---|
| `snapshot-file` | `filter_snapshot_files` at consolidate | the machine snapshot's export stamp | **yes** |
| `snapshot-section` | `filter_snapshot_files` at consolidate | the machine snapshot's export stamp | **yes** |
| `settings-key` | `filter_settings_blob` at consolidate | the machine snapshot's export stamp | **yes** |
| `plugin` | `plan_convergence` | `""` (always suppress) | no |
| `hook-registration` | `plan_hook_wiring` | `""` (always suppress) | no |

`plugin` and `hook-registration` are local-state filters with no cross-machine clock race,
so they are out of scope. `SnapshotPropagator.apply` is also out of scope: it passes `""`
for the reason its own comment gives, and that reasoning is unaffected.

**In scope:** the consolidate fold, for the three snapshot-carried kinds.

**Out of scope:** deletion propagation (`BundleDeletionLedger` owns that); clock skew
between machines (timestamps are already compared lexicographically fleet-wide, and this
design neither improves nor worsens that); removing the `resolve-rejection` prompt.

## 4. Approach

Provenance travels **inside the machine snapshot**, and the machine's own previous
snapshot is the baseline that produces it.

`machines/<id>.json` is already per-machine, already in the repo, and already
conflict-free by construction. Reading it before overwriting it gives export everything
it needs to answer "did this unit change?" — with no second file to keep in step.

The alternative considered was a separate `machines/provenance/<id>.json` index mirroring
`BundleDeletionLedger`'s per-machine export index. It is the more orthodox
single-responsibility split, but it introduces two documents describing the same export
that can silently disagree — precisely the failure class this feature exists to prevent.
Co-locating them makes that divergence structurally impossible.

Filesystem `mtime` was rejected outright. It is per-file, so it cannot address sections or
settings keys — three of the five kinds — and editing any section of `CLAUDE.md` would bump
the whole file's mtime and resurrect an unrelated rejected section in the same file. It is
also reset by `git checkout` and rewritten by editors that save whole files.

## 5. Architecture

### 5.1 One shared address vocabulary

The sharpest risk is a repeat of the tier-1 marker bug found in phase 2's final review:
one side computes an address one way, the other recomputes it differently, they stop
matching, and the feature degrades silently.

`filter_snapshot_files` already walks exactly the units that need stamping — files, then
`config_sync_merge._parse_sections` for `.md` sections — but that walk is entangled with
filtering. Extract it:

```
iter_addressable_units(files) -> Iterator[AddressableUnit]
AddressableUnit = (kind, address, payload)
```

It computes addresses through the **existing** `SnapshotFileAddressor`,
`SnapshotSectionAddressor` and `SettingsKeyAddressor` — never a parallel implementation.
Both the filters and export consume this one iterator. Neither owns it.

Extracting the walk must not change filtering behavior. `filter_snapshot_files` has a
documented non-obvious invariant — a file with no rejected section is passed through as
the original object, never round-tripped through `_parse_sections`/`rejoin_sections`,
because that round-trip is not lossless for a document ending in a bodiless heading. The
extraction preserves it.

### 5.2 Seams (dependency inversion)

- **`ContentProvenanceStamper`** — `stamp(files, previous, now) -> dict`. Injected into
  `SnapshotPropagator` through its constructor, alongside the existing `policy` and
  `export_filter` injection points. Export depends on the abstraction; hashing sits behind
  it and is trivially faked in tests.
- **The provenance reader**, passed into the filters. The public `source_timestamp: str`
  signature does **not** change. Instead the filters take an optional `provenance=None`
  defaulting to a null object that always answers with the bare string — the idiom
  `NullRejectionPolicy` already establishes. Every existing caller and test is unaffected;
  the new behavior is opt-in at the call site.
- **`iter_addressable_units`** — the shared vocabulary both sides depend on.

Responsibilities stay separate: the stamper decides *when content changed*, the policy
decides *whether it is rejected*, the filter decides *what to withhold*.

## 6. Data model

One new top-level key in the machine snapshot. `timestamp` is untouched and keeps its
current meaning as the export time.

```json
{
  "machine_id": "machine-a",
  "timestamp": "2026-08-04T09:00:00+00:00",
  "files": { "...": "..." },
  "provenance": {
    "snapshot-file": {
      "rules/a.md": { "changed_at": "2026-07-30T11:00:00+00:00", "hash": "<sha1>" }
    },
    "snapshot-section": {
      "<section address>": { "changed_at": "2026-08-01T14:00:00+00:00", "hash": "<sha1>" }
    },
    "settings-key": {
      "[\"permissions\",\"defaultMode\"]": { "changed_at": "2026-06-02T08:00:00+00:00", "hash": "<sha1>" }
    }
  }
}
```

Keyed kind-then-address, mirroring how rejections are keyed, so lookup is two dict hits
with no parsing. Each entry carries both `changed_at` and the `hash` that justified it —
the hash is what the next export compares against.

Timestamps are UTC ISO 8601 strings compared lexicographically, per the existing
fleet-wide convention. They are never parsed.

Units that vanish between exports simply drop out of the map. No tombstones — deletion
propagation belongs to `BundleDeletionLedger`.

### 6.1 Nesting

Units overlap: a file contains sections, a settings subtree contains leaves. **Each
addressable unit gets its own hash and its own `changed_at`, independently.**

- Editing section A does **not** touch section B's provenance. This is the resurrection
  fix.
- Editing section A **does** bump the enclosing file's `changed_at`, because the file's
  content genuinely changed. A whole-file rejection therefore resurrects when any part of
  that file is edited.
- Likewise, rejecting the `permissions` subtree and then editing
  `permissions.defaultMode` brings the subtree back.

This is deliberate. For a *file* rejection the unit of intent is the file, and any edit to
it is a change to the thing that was declined — the same rule phase 1 already applies,
now measured accurately. It is categorically different from the `mtime` failure, where a
whole-file change resurrected a rejected *section*: something finer than what actually
changed. Per-unit hashing cannot do that.

## 7. Data flow

**Export** (`SnapshotPropagator.export`) gains a read-before-write:

1. Build `files` as today.
2. Read this machine's existing `machines/<id>.json` for its previous `provenance` map.
3. For each unit from `iter_addressable_units(files)`, hash the payload:
   - hash matches the previous entry → carry `changed_at` forward unchanged;
   - hash differs, or the unit is new → stamp `changed_at = now`.
4. Write `provenance` into the snapshot beside `files`.

**Consolidate** (`cmd_consolidate`) builds a provenance reader from
`snapshot.get("provenance")` and passes it to `filter_snapshot_files` and
`filter_settings_blob` alongside the existing `source_timestamp`.
`TimestampedRejectionRule` then compares each rejection against *that unit's*
`changed_at` rather than the export clock.

A machine holding rejected-but-untouched content re-exports it carrying a `changed_at`
older than the rejection, so it stays suppressed and convergence is automatic. A machine
genuinely re-adding the content stamps a fresh `changed_at` and correctly overrides.

## 8. Mixed-version fleet

Machines will run different engine versions for some window. A snapshot with no
`provenance` key — or a unit absent from an otherwise-present map — **falls back to
`snapshot["timestamp"]`**: exactly today's behavior, for that machine only.

An un-upgraded machine can therefore still resurrect until it upgrades, and the fleet
self-heals as machines update. No flag day, and no version ever behaves worse than the
status quo.

## 9. Failure modes

Provenance is an optimization over a fallback that already exists and is already
correct-if-conservative. Rejection data is not. They get different rulings, and the
asymmetry is deliberate: bad provenance costs one avoidable `resolve-rejection` prompt,
while bad rejection data silently reinstates content the operator declined. Only the
second justifies halting the fleet.

| Case | Ruling |
|---|---|
| `provenance` key absent | Fall back to `snapshot["timestamp"]` (§8). |
| Unit missing from an otherwise-present map | Same fallback. A file created between exports lands here naturally. |
| `provenance` malformed — not a dict, or an entry missing `changed_at` | Fall back for that unit and **warn**, naming the machine. Not fatal. |
| Previous snapshot unreadable at export | Stamp every unit `now` and warn. Conservative in the safe direction: can cause one spurious resurrection, never a spurious suppression. |
| Corrupt rejection ledger | Unchanged — `CorruptRejectionLedgerError`, still fatal. |

**The silent failure mode.** If `iter_addressable_units` ever disagrees with the
addressors the filters use, every lookup misses, every unit falls back, and the feature
degrades to today's behavior **with no error at all**. That is the tier-1 marker bug's
exact signature. §5.1's single shared iterator is the structural defense; §10's drift
guard is the test that catches a bypass.

## 10. Testing

**Headline test, written first and observed failing.** Two machines; A rejects content; B
still holds it unchanged; B re-exports; consolidate runs; assert the content is still
absent. This fails against current code — it *is* the bug. Its twin asserts B genuinely
editing the content brings it back.

**Drift guard.** Assert the address set `iter_addressable_units` produces for a given
`files` dict is exactly the set the filters query for the same input. If anyone
reimplements addressing on either side, this fails loudly instead of the feature
degrading silently. The single most important test here.

**Sibling isolation and nesting**, pinning §6.1 in both directions: editing section A must
not resurrect rejected section B in the same file; editing any section must resurrect a
whole-file rejection.

**Carry-forward stability.** Unchanged content re-exported three times still reports its
original `changed_at` — not a value sliding forward each run. A sliding stamp passes a
single-export test and reintroduces the bug over time.

**Mixed fleet.** A provenance-less snapshot falls back and can still resurrect, while an
upgraded machine in the same fold does not. Per-machine, not fleet-wide.

**Degradation paths** from §9: unreadable previous snapshot stamps `now` and warns;
malformed provenance falls back per-unit and warns; neither aborts.

**Extraction safety.** The §5.1 refactor must not change filtering behavior — in
particular the bodiless-final-heading round-trip invariant. Existing
`filter_snapshot_files` coverage must pass untouched.

All against production-shaped state: real snapshots with real timestamps, no doubles on
the path under test. Phase 2 had to add a remediation task (10b) to enforce exactly this
after two of three end-to-end walks turned out unable to fail. The repo's mutation gate
should be checked against the drift guard and carry-forward tests specifically, since both
can pass vacuously.

## 11. Constraints inherited

- No new runtime dependencies. Stdlib only (`hashlib`, `json`, `datetime`) — the engine
  runs under `bin/mente-python`, which may resolve to a bare system interpreter.
- `uv run black .` owns formatting; `uv run ruff check --fix .` clean. ruff N818: exception
  class names end in `Error`. Note black (26.5.1, py314) rewrites a parenthesized
  except-tuple with no `as` clause into the unparenthesized PEP 758 form and
  `test_the_repo_is_black_clean` enforces black's output; two narrow `# fmt: off` fences
  exist for this and are the established precedent.
- Descriptive names throughout, including in comprehensions and generator expressions.
- Cross-script imports inside `scripts/` are deferred imports inside functions —
  `scripts/` is a flat set of siblings, not a package.
- Never touch the operator's real `~/.claude` from a test; `config_sync.py` computes
  `HOME`/`CLAUDE_DIR` at import time, so only the `claude_home` fixture reaches them.
- Scope remains a correctness boundary: shared-state writers get a network-only policy,
  local-state writers get the composite.
- A rejection withholds; it never deletes.
- Baseline suite at time of writing: **1403 passing**.

## 12. Follow-ups this does not do

- `resolve-rejection` remains, its meaning narrowed: with convergence automatic, it stops
  being required for correctness and becomes "this content is still on your disk — remove
  it here too, or keep it?". The withholds-never-deletes invariant is unchanged, and one
  machine can still overrule the network.
- The duplicate composite-policy composition roots (`config_sync.local_rejection_policy`
  vs `config_sync_propagators.apply_propagators`) remain unmerged. Tracked from phase 2's
  final review; a refactor, not a defect.
- Phase 1's design doc says automatic convergence "needs per-content provenance, which is
  phase 2". Phase 2 deferred it here. That sentence is corrected as part of this work.
