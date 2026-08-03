# Rejection ledger — reject and forget pulled config

**Date:** 2026-08-03
**Project:** mente-apex-plugin — config-sync engine
**Scope:** snapshot config (CLAUDE.md, `memory/`, `rules/`, `settings.json`) + plugin plan actions
**Semantics:** per-rejection scope (local veto or network tombstone), timestamped so a newer re-add wins

---

## 1. Problem

Content pulled from another machine and declined at the apply gate comes back at
the next sync, every sync, forever. There is no way to say "I have seen this and
I do not want it."

The mechanism is `cmd_consolidate` (`scripts/config_sync.py:882`). It seeds
`base_files` from the **existing** `consolidated/snapshot.json`, then folds each
`machines/*.json` on top in ascending `timestamp` order. Nothing is ever
subtracted, so the consolidated snapshot is a ratchet: once content enters it,
it is immortal.

Observed on 2026-08-03. Three superseded sections had been deleted from
`~/.claude/CLAUDE.md`, and five crashing `python3` hook registrations from
`settings.json`. **No machine snapshot carried any of them** — all three machines
were clean. The consolidated snapshot alone carried them, and `propagate-apply`
would have restored a 4,630-char `CLAUDE.md` (larger than the 4,500-char original)
and taken `hooks.PreToolUse` from 6 registrations back to 10. The only available
answer was to skip the apply step entirely, which fixes nothing and defers the
same decision to the next sync.

The 2026-07-08 bundle-deletion design named this exact gap as a non-goal:
*"propagating deletions inside snapshot config (CLAUDE.md / `memory/` / `rules/`)
— that needs section-level tombstones and stays union-only for now"* and *"a
'keep it here only' per-machine suppression state."* This design takes on both.

**Goal:** declining pulled content records a durable decision, so it is never
re-proposed — on this machine, or on the whole network, at the operator's choice.

**Non-goals (YAGNI):** rejecting skill/agent **bundles** (that is
`BundleDeletionLedger`'s job and it already works); pre-emptive rejection of
content that has not arrived yet; auto-expiry of old rejection records; clock-skew
correction between machines.

## 2. How DIP shaped this

The new responsibility — *tracking what was refused* — is a new abstraction,
`RejectionPolicy`, injected into its consumers through the constructor exactly as
`BundleDeletionLedger` and `BundleExportFilter` already are.

- `cmd_consolidate` and `SnapshotPropagator` take `policy: RejectionPolicy | None`.
  They never learn where rejections are stored, nor how any kind is addressed.
- Storage is behind the same interface twice — `LocalRejectionStore` and
  `SharedRejectionStore` — so the caller cannot tell which one answered.
- Addressing is a second abstraction, `UnitAddressor`, one implementation per
  rejectable kind, registered in the composition root. Adding a fifth kind is a
  new class, not an edit to consolidate or the propagator (OCP).
- The timestamp comparison lives in exactly one place, `TimestampedRejectionRule`,
  rather than being re-derived at each call site.
- Tests substitute a store rooted at `tmp_path` and a fake clock. No globals, no
  singletons, no module-level state.

Defaulting `policy` to `None` means "no policy → today's behavior", so the
existing suite is untouched by construction.

## 3. New units — `scripts/config_sync_rejections.py`

### `RejectionRecord`

Frozen dataclass:

```
id            short content hash of (kind, address) — stable id for `unreject`
kind          snapshot-section | snapshot-file | settings-key
              | hook-registration | plugin
address       kind-specific, produced by that kind's UnitAddressor
tier          which identity tier produced `address` (hook-registration only)
scope         local | network
rejected_at   UTC ISO 8601
machine_id    who rejected it
reason        optional free text
revives       rejection id this record overrules, or None (see §5)
```

`id` hashes `(kind, address)` only — deliberately **not** `scope`. A target has at
most one active record; re-rejecting it with a different scope updates that record
rather than creating a second one that could disagree with itself.

### `RejectionPolicy` (Protocol)

```
is_rejected(target: RejectionTarget, source_timestamp: str) -> bool
record(record: RejectionRecord) -> None
forget(rejection_id: str) -> None
all() -> list[RejectionRecord]
```

`source_timestamp` is the timestamp of the snapshot contributing the content.
`TimestampedRejectionRule` implements the rule: a target is suppressed unless its
source is **strictly newer** than `rejected_at`. Equal timestamps suppress. This
is the same shape as `BundleDeletionLedger.is_deleted(..., bundle_exported_at)`
(`scripts/config_sync_propagators.py:450`), and that method can later delegate to
this rule.

### Two stores, one interface

The scope flag forces the split — a local veto must never be committed, or it
leaks to every other machine:

- `LocalRejectionStore` → `~/.claude/config-sync-rejections.json`. Never committed.
- `SharedRejectionStore` → `rejections/<machine_id>.json` in the config repo.
  Git-tracked, one file per machine so it converges without merge conflicts — the
  same per-file pattern `machines/<id>.json` and `bundles/.index/<id>.json` use.
- `CompositeRejectionPolicy` fans a query across both and unions the answers.

**Which consumer sees which scope** — this is a correctness boundary, not a
preference. `cmd_consolidate` is handed a **network-only** policy: it writes shared
state, and a local veto leaking into `consolidated/snapshot.json` would silently
impose one machine's preference on the whole network. `SnapshotPropagator.apply`
and `plugins-plan` are handed the **composite**: they write local state only, where
honouring both scopes is correct (network records are normally already gone by
then, so the composite is belt-and-braces for a machine that applies without
having consolidated).

### `UnitAddressor` (Protocol)

`identify(unit) -> address` and `matches(address, unit) -> bool`, one per kind:

| Kind | Address example | Identity comes from |
|---|---|---|
| `snapshot-section` | `CLAUDE.md#("## Memory protocol", 0)` | existing `_parse_sections` key (`config_sync_merge.py:251`) |
| `snapshot-file` | `rules/some-rule.md` | the snapshot `files` dict key |
| `settings-key` | `enabledPlugins["open-memory@open-memory"]` | the JSON key path itself |
| `hook-registration` | see §3.1 | existing `config_sync_hooks` helpers |
| `plugin` | `open-memory@open-memory` | `plugins-plan` action target |

`_parse_sections` already returns `(heading, nth_occurrence)` keys that survive
repeated headings, so section identity is borrowed from tested code rather than
invented.

`settings.json` needs **two** addressors, not one. A key path into the deep-merged
object (`enabledPlugins`, `permissions.defaultMode`) is stable by construction and
needs nothing clever. A hook registration is a *list element* with no natural key,
and that is the hard case — separating them keeps the easy kind from inheriting
the hard kind's machinery (ISP), and keeps each addressor to one reason to change.

### 3.1 `HookRegistrationAddressor` — three identity tiers

Keying a registration on its whole command string is a known defect in this
codebase: `script_key_of` (`config_sync_hooks.py:59`) exists precisely because
changing an interpreter (`python3 X` becoming `${ROOT}/bin/py X`) minted a fresh
id, leaving the previous registration unmatched forever as a second, eventually
broken copy. A rejection keyed that way would be just as brittle — the interpreter
path is exactly what changes when a tool is reinstalled.

So identity resolves in tiers, **most stable first**, falling to the next tier only
when a tier is ambiguous:

| Tier | Address | Survives |
|---|---|---|
| 1 | `hooks/<hook_id>` | interpreter change, relocation, matcher edit — anything. Available only when the command carries a `# config-sync:<id>` marker (`hook_id_in`). |
| 2 | `hooks/<event>/<matcher>/<script basename>` | interpreter change and relocation. Uses `script_name_of`, which reads both the `${TOKEN}` and the localized absolute form. |
| 3 | `hooks/<event>/<matcher>/#<sha1 of strip_marker(command)>` | nothing — exact match. The floor for commands with no identifiable script, such as opaque shell fragments. |

**Ambiguity falls downward, to the more specific tier.** This is not theoretical:
today's `enforce_gates.py` case has two registrations under the *same* event and
matcher whose basenames both read `enforce_gates.py`, differing only in full path
(`~/.claude/mente-apex/…` vs `~/Projects/mente-apex-memory/…`). Tier 2 is ambiguous
there, so resolution falls to tier 3, where the full path distinguishes them — and
brittleness is then *correct*, because the operator rejected one specific copy.
This is the same situation `hooks-doctor` already reports as the advisory
`duplicate-script` finding.

The rule for a claimed key is inherited verbatim from `registrations_by_script`:
never guess between two matches. If even tier 3 is ambiguous — two byte-identical
registrations under one event and matcher — every match is rejected together, since
they are indistinguishable and an exact duplicate is precisely what one wants gone.

`registrations_by_script` itself is **not** reused: it iterates `registered_hooks`,
which yields only config-sync's own marked registrations, and 2 of the 3 hooks in
the motivating case were hand-added and unmarked. The addressor does its own scan
over `hook_sites`, reusing the pure helpers (`hook_id_in`, `script_name_of`,
`strip_marker`, `choose_script_path`) rather than duplicating their logic.

The record stores the tier alongside the address, so matching recomputes only that
tier rather than re-running resolution.

## 4. Data flow

### Creating a rejection

Two entry points, one code path. `propagate-apply` reports what it would write;
the SKILL's Step 4 gate gains a third answer ("reject forever") which calls the
same command available by hand:

```
reject <kind> <address> [--scope local|network] [--reason "..."]
rejections                              # list: id / kind / scope / age / reason
unreject <id>                           # undo, either scope
resolve-rejection <id> remove|keep      # the other-machine gate
```

### Enforcing it — three filter points

1. **`cmd_consolidate`** subtracts *network* rejections during the fold, including
   from `base_files` seeded by the prior consolidated snapshot. **Filtering
   `base_files` is the fix** — that is the ratchet. Each fold step passes the
   contributing snapshot's `timestamp` as `source_timestamp`, so "newer re-add
   wins" falls out of the existing ascending-order loop with no new provenance
   tracking.
2. **`SnapshotPropagator.apply`** subtracts *local* rejections. The content stays
   in the shared snapshot for everyone else; this machine simply never writes it.
3. **`plugins-plan`** drops rejected plugin actions before returning, so a plugin
   you do not want stops appearing in the plan every sync.

### Converging other machines

A network rejection ships as `rejections/<machine_id>.json`. On another machine's
next sync, `propagate-apply` returns a `rejection_removals` list — the ledger
**records** (not bare addresses: the prompt needs `machine_id` and `rejected_at`,
and `resolve-rejection` takes `id`) behind the content withheld from that apply —
and the SKILL prompts as it already does for bundle deletions:

> `## Memory protocol` was rejected on `Mac.fritz.box` at 09:00 — remove here, or keep?

- `remove` — records a **local** rejection for the same address, so this machine
  withholds the content from the next apply onward. It is a write, not a no-op:
  agreeing silently would leave the consolidated snapshot re-writing the content
  here on every sync.
- `keep` — the content returns for everyone, mirroring `resolve-deletion`'s keep
  branch clearing a tombstone. One machine can always overrule the network.

**Convergence is bounded in phase 1.** A network rejection converges only once no
machine still carries the content. Every machine exports before anyone
consolidates, and an export is stamped with the time it ran, so a machine that
still holds the content re-adds it as content strictly newer than the rejection —
an unchanged re-export is, to this engine, indistinguishable from a deliberate
re-add. Answering `remove` on each such machine is what finishes the job.
Automatic convergence needs per-content provenance, which is phase 2.

## 5. Failure modes

**Fail closed.** A corrupt or unreadable rejection store aborts `consolidate` /
`apply` with the parse position. It does **not** degrade to "no rejections" —
that would silently resurrect precisely the content the operator killed, which is
the bug this feature exists to prevent.

| Case | Ruling |
|---|---|
| Address matches nothing | Error, listing near-miss addresses. A typo must not sit in the ledger forever doing nothing. |
| Rejection would empty a whole file | Refuse unless `--force`, reusing the `_guard_mass_deletion` precedent (`config_sync_propagators.py:505`). |
| `source_timestamp == rejected_at` | Rejection wins. A re-add must be **strictly newer** to count as fresh intent. |
| Machine A wants to keep what B rejected | A cannot write B's file. `resolve-rejection keep` writes a **revival record into A's own** shared file — a `RejectionRecord` with `revives` set to B's rejection id and a newer `rejected_at`. `CompositeRejectionPolicy` treats a target as suppressed only when no revival record newer than its rejection exists. Conflict-free: no cross-machine writes. |
| Clock skew between machines | Known limit, documented. Same exposure `BundleDeletionLedger` already carries. Not solved here. |
| Bundles (skills / agents) | Out of scope; `_SKIP_APPLY_PREFIXES` already keeps them out of snapshot handling. |

## 6. Testing

- **Unit** — each `UnitAddressor` (identify→matches round trip, repeated headings);
  `TimestampedRejectionRule` at older / newer / **equal**; each
  store (round trip, absent file, corrupt file); `CompositeRejectionPolicy` fan-out
  and revival precedence (revival newer than rejection un-suppresses; older does not).
- **Hook identity tiers** — a dedicated suite, since this is the part most likely
  to be wrong: tier 1 chosen when a marker exists; tier 2 matching the *same*
  registration after its interpreter is swapped (`python3 X` → `/abs/uv/bin/python X`)
  and after relocation; tier 2 ambiguity (two `enforce_gates.py` under one
  event+matcher) falling to tier 3 and distinguishing them by full path; tier 3
  ambiguity rejecting every byte-identical match; an unmarked hand-added hook
  addressable at all, which `registrations_by_script` alone would miss.
- **Scope isolation** — a `local` record must never influence the consolidated
  snapshot. Assert it directly: record a local rejection, consolidate, and confirm
  the content survives in shared state while `apply` still withholds it locally.
- **Contract / LSP** — both stores run against **one shared `RejectionPolicy`
  suite**, so substitutability is proven rather than assumed.
- **Regression, the one that matters** — consolidate where the prior
  `consolidated/snapshot.json` carries the content and **no machine snapshot
  does**, with a network rejection recorded. The result must not contain it. This
  reproduces 2026-08-03 exactly; without it the feature can pass everything else
  and still not fix the problem.
- **Non-regression** — the existing suite runs unchanged (`policy=None`).
- **Mutation gate** — `TimestampedRejectionRule` is prime `>` / `>=` mutant
  territory and goes in scope for `scripts/mutation_gate.py`.

## 7. Deliverables

- `scripts/config_sync_rejections.py` — the new module (policy, stores, rule,
  addressors for `snapshot-section` / `snapshot-file` / `settings-key` / `plugin`).
- `scripts/config_sync_rejection_hooks.py` — `HookRegistrationAddressor` and its
  tier resolution, kept separate because it is the only addressor with a
  non-trivial algorithm and it is the one that depends on `config_sync_hooks`.
- `scripts/config_sync.py` — `cmd_reject`, `cmd_rejections`, `cmd_unreject`,
  `cmd_resolve_rejection`; `policy` parameter threaded into `cmd_consolidate`.
- `scripts/config_sync_propagators.py` — `policy` parameter on
  `SnapshotPropagator`; `rejection_removals` in its `ApplyResult`.
- `scripts/config_sync_plugins.py` — plan filtering.
- `skills/config-sync/SKILL.md` — Step 4 reject branch, Step 4e removal prompts,
  `Rejected : N` in the Step 7 summary.
- Tests per section 6.
