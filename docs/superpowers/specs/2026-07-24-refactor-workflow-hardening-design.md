# Design — refactor-workflow hardening (three orchestration fixes)

**Date:** 2026-07-24
**Status:** approved (design), pending implementation plan
**Branch:** `fix/transient-findings-draft-lifecycle`
**Theme:** the orchestrator does the robust thing up front, so subagents and the
apply phase can't be tripped up by state the workflow left ambiguous.

Three independent gaps in the shared refactor orchestration, surfaced by one
`code-quality` run, fixed together because they touch the same layer and share one
philosophy: **make the orchestrator own what must be reliable — workspace lifecycle,
shared scanning, and conflict resolution — instead of leaving it to each subagent or
to apply time.**

| # | Concern | Primary file(s) |
|---|---------|-----------------|
| C1 | transient `findings-draft.md` lifecycle | `docs/refactor-workflow.md` |
| C2 | Phase-0 shared symbol index (pre-collect the greps) | `skills/code-quality/SKILL.md` |
| C3 | conflict/exclusion resolution at the decision gate | `docs/refactor-workflow.md`, `skills/code-quality/{SKILL.md, references/report-template.md, agents/consolidator.md}` |

---

## C1 — transient `findings-draft.md` lifecycle

### Problem

Each lens runs a generator–critic pair: **Phase 1 analyzer** (read-only) writes
candidate findings to `docs/reports/<lens>/findings-draft.md`; **Phase 2 reviewer**
consumes that draft and writes the durable templated report to
`docs/reports/<lens>/<LENS>-REPORT-<YYYY-MM-DD>.md`. The draft is a **transient
hand-off** whose sole consumer is the reviewer, but two asymmetries make it behave as
if durable:

- the final report is written to a **dated** path → never collides across runs;
- the draft is written to a **fixed** path and is **never deleted** by any phase.

**Observed (2026-07-22 → 2026-07-24):** a new run tried to write `findings-draft.md`
while the prior run's copy still sat at the exact fixed path. The Read-before-Write
guard correctly blocked the un-read overwrite. Worse than the block: a fixed-path
draft that survives between runs makes fresh and stale content indistinguishable and
invites an unsafe Bash-bypass that clobbers the prior file.

Root cause: the deliverable is dated and durable; the transient hand-off got a fixed
name and no reaper.

### Design (all in `docs/refactor-workflow.md`)

- **Edit 1 — Phase 2 primary reaper.** After the orchestrator confirms the report
  **exists and parses** (the fan-in it already does under "artifacts always
  terminal"), it **deletes `docs/reports/<lens>/findings-draft.md`**. Deletion is
  conditional on a parseable report: if the reviewer died and left no report, the
  draft is **kept** (only evidence of the partial run) and the existing coverage-gap
  path applies.
- **Edit 2 — Phase 0.3 crash-safety pre-clear.** When creating
  `docs/reports/<lens>/`, also remove any stale `findings-draft.md` left by a run
  that crashed between Phase 1 and end-of-Phase-2. Clears only the transient draft,
  never dated reports.
- **Edit 3 — lifecycle sentence** near the cast/guardrails: *"`findings-draft.md` is
  transient: written by the analyzer (P1), consumed by the reviewer (P2), deleted by
  the orchestrator once the report is durable (end of P2). Only the dated report
  persists."*

### Rejected

- **Date the draft** — no collision, but drafts accumulate; contradicts "transient."
- **Memory-to-memory hand-off** — flaky; forces the orchestrator to shuttle a large
  findings blob between subagents.
- **Read-then-overwrite in the analyzer** — the Bash-bypass instinct in disguise;
  makes the analyzer ingest a stale artifact and still leaves fresh/stale ambiguity.

---

## C2 — Phase-0 shared symbol index (collect the greps once)

### Problem

The `code-quality` umbrella already builds a **shared index** in Phase 0 — the scoped
**file list** and the **import graph** (built once with `grimp`/`madge`) — and hands
it to all six analyzers so "imports are answered from this graph, not re-grepped"
(`code-quality/SKILL.md` Phase 0 + Phase 1 brief). But the import graph is only *one*
of the tree-wide scans the lenses share. Each analyzer still independently
re-enumerates **definitional structure** its rubric needs:

- **solid** — class names `Manager|Handler|Service|Processor|Controller`, constructor
  calls to `db/http/fs/smtp/queue`, `isinstance`/`instanceof` sites;
- **ddd** — controllers/models carrying business logic;
- **test-quality** — test refs diffed against **current source symbols**;
- **gof** — global-state / singleton sites.

Six analyzers re-globbing and re-grepping the tree for the same class/function/method
inventory is the same 6× waste the import graph already removed for edges — for
symbols instead.

### Design (in `skills/code-quality/SKILL.md`; umbrella-only)

Extend the Phase-0 shared index with a third artifact: a **symbol index** — every
class / function / method definition with `file:line`, name, and rough LOC — built
**once** with a real tool when reachable, degrading exactly like the import graph:

> **`ast-grep`** (primary; already referenced in Phase 1 for structural queries)
> → **`ctags`** (fallback) → **agent-read of the scoped file list** (last resort,
> recorded as a coverage note).

Then generalize the existing rule. Alongside *"imports are answered from this graph,
not re-grepped,"* add: **"definitions and call-sites are answered from the shared
symbol index, not re-enumerated by each analyzer."** Each analyzer's remaining
*semantic* grep (SOLID's discriminator conditionals, GoF's global-state) still
runs — but scoped to the file list against the pre-built corpus, not as a fresh
full-tree sweep.

Single-lens runs are unaffected (one analyzer, no fan-out redundancy); this lives in
the umbrella only.

### Rejected

- **Centralize each lens's actual greps in the umbrella** — have Phase 0 run every
  lens's rubric greps and hand down results. Rejected: forks each lens's rubric into
  the orchestrator and couples it to lens internals, violating the plugin's **"Reuse,
  don't fork"** guardrail. The shared *index* is lens-agnostic structural fact; the
  *interpretation* stays in each lens.

---

## C3 — conflict/exclusion resolution at the decision gate

### Problem

The workflow's decision gate models **cohesion** (`## Grouped changes` = "these apply
together") but has **no concept of exclusion** ("these can't coexist"). The
consolidator already *detects* conflicts (`consolidator.md` rule 7) and writes them as
a **prose line** (`report-template.md` — "Unresolved tensions (surfaced, not
auto-decided)"), and the umbrella's Phase 3 says to *present* them
(`SKILL.md:150`). But the **shared** Phase 3 — where the approval mechanics actually
live (tier / group / id) — knows nothing about conflicts, so tier approval ("apply
all Med") pulls in **both** sides of a mutually-exclusive pair. The conflict then
only bites at apply time when the two edits fight.

**Observed:** two Med-risk findings on the same file pointed in opposite directions
(`apply(A) ⟹ ¬apply(B)`). The tension was written into the report but never wired into
the apply set; it surfaced only when the apply-time agent noticed and stopped. This
is the *hard* kind of conflict — a fork — stronger than the philosophical
Singleton↔DIP tension the design was built around.

### Design

- **Structured conflict, not prose** (`consolidator.md`, `report-template.md`). The
  consolidator emits a `## Conflicts` block parallel to `## Grouped changes` — each
  entry: the rec IDs, the axis of disagreement, and the consequence
  (`apply solid/med-2 ⟹ drop ddd/med-1`). The gate consumes it mechanically.
- **Resolve at the shared Phase 3, before ordering** (`docs/refactor-workflow.md`
  Phase 3). Before the apply order is computed, every declared conflict is resolved by
  an explicit **either/or** (winner, or "neither") — symmetric to per-item High-risk
  confirmation. **Blanket/tier approval cannot resolve a conflict:** "apply all Med"
  is undefined over a mutually-exclusive pair, so the gate intercepts and forces the
  pick **even under a pre-authorization**. State this explicitly (pre-auth covers
  independent recs; a fork has no "all" answer).
- **Ordering is undefined until the fork resolves.** A mutual exclusion is a branch,
  not a dependency; the dependency-aware apply order can't be linearized while both
  are approved. Resolution is therefore upstream of Phase 4, not a step inside it.
- **Apply-time refuses, never decides** (`docs/refactor-workflow.md` Phase 4). If a
  conflict reaches Phase 4 unresolved, the implementer stops and kicks back to the
  gate; it must not pick a winner. (The apply-time stop-and-confirm behavior is
  correct; this fix moves the catch earlier so apply rarely has to.)
- **Honest ledger for the loser.** The dropped rec's `Status:` reads
  `skipped (lost conflict to <id>)`, not a bare `skipped (not approved)`, so a
  returning session or re-run sees *why* it was excluded and doesn't resurrect it.
- **Regression guard.** One line in the Phase 3 checklist: *"every declared conflict
  is resolved before the apply order is computed."*

### Rejected

- **Keep conflicts as an informational note** (status quo) — insufficient: presenting
  is not resolving, and the apply set is still computed as if the recs were
  independent, which is the bug.

---

## Scope & impact (all three)

- **C1** — one file: `docs/refactor-workflow.md`. All seven lenses inherit it; the
  umbrella (merges reports, not drafts) and analyze-only lenses are safe.
- **C2** — `skills/code-quality/SKILL.md` only (Phase 0 build + Phase 1 brief).
  Umbrella-only; no per-lens or agent-doc change.
- **C3** — `docs/refactor-workflow.md` (Phase 3 + Phase 4) and the umbrella's
  `consolidator.md` / `report-template.md` / `SKILL.md` Phase 3. Single-lens runs
  rarely produce cross-lens conflicts but inherit the same gate mechanics for any
  intra-lens fork.
- No changes to lens rubrics, the TDD apply engine's contract, or the analyzer/
  reviewer role split.

## Verification

Behavioral (the changes are orchestration prose), exercised on a real run:

- **C1** — run a lens twice on the same target: the second Phase 1 succeeds with no
  Read-before-Write block, and after Phase 2 the draft is **absent** while the dated
  report is present. Leave a stale draft in place → Phase 0.3 clears it before Phase
  1. A Phase 2 that produces no parseable report **keeps** the draft.
- **C2** — run `/code-quality`: the shared index in `docs/reports/code-quality/`
  contains the symbol index; analyzer briefs cite it; confirm (via the tool-detection
  note) that no analyzer re-enumerates definitions the index already holds, and that
  the agent-read degrade path is recorded when no tool is reachable.
- **C3** — feed the gate a report with a `## Conflicts` entry under a blanket "apply
  all Med" pre-authorization: the gate still **stops** and forces the either/or; the
  loser lands `skipped (lost conflict to <id>)`; the apply order is computed only over
  the reduced set. A conflict reaching Phase 4 unresolved makes apply **halt**, not
  choose.
