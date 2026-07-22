# Grouped change as a first-class pipeline unit — design

**Date:** 2026-07-22
**Project:** mente-apex-plugin — code-quality review lenses
**Status:** Approved (brainstorming complete, ready for implementation plan)
**Origin:** code-quality umbrella QoL item **#2 of 6** — deferred to its own brainstorm because it
changes the *shared* gate+apply contract reused by every apply-capable lens. Sibling items #1
(filename stems → `-REPORT-`), #3 (Status/Apply-log spec centralized), #5 (structure tests assert
ID shape) landed 2026-07-22; #4 (unify cross-ref field → `Related`) and #6 (explicit anchor links)
are separate open items.

---

## 1. Problem

The review lenses (`/solid`, `/gof`, `/ddd`, `/clean-code`, `/clean-architecture`) and the umbrella
`/code-quality` share one workflow: **find** problems → write a tiered report → **gate** (human
approves recs) → **apply** (one TDD refactor job per approved rec/chain, suite green after each).

The umbrella consolidator already recognises that **several findings are often one physical edit**.
Its report has a `## Grouped changes` section (`skills/code-quality/references/report-template.md:78`)
naming a **Primary** finding plus typed related findings, and each finding carries a typed `Related:`
line. Real example from the 2026-07-22 audit: *"Extract `config_sync_fs.py` leaf"* is one edit that
resolves `clean-arch/major-1` (Primary), `clean-arch/major-2`, `solid/major-5`, and `clean-arch/minor-2`.

**But that grouping evaporates downstream.** The two later phases throw it away:

- **Phase 3 gate** (`docs/refactor-workflow.md:85-91`) lets the human approve only **by tier** ("all
  Major") or **by individual ID**. There is no way to approve *"do the `config_sync_fs` extraction"* as
  one decision.
- **Phase 4 apply** (`docs/refactor-workflow.md:135-137`) ignores the group entirely and **re-derives**
  batches from a **file-overlap heuristic** ("recs touching the same file form a chain"). That heuristic
  can spin up several TDD jobs for what is one edit, or miss that a finding was already resolved by a
  sibling's change.

**Goal:** make a *Grouped change* a first-class unit carried end-to-end — approvable by title at the
gate, and applied as **one** TDD job — so the pipeline executes what the report already declares, and
stays fully auditable in the report.

## 2. The group model

A **group** is one physical edit that resolves 2+ findings. Its members have three roles:

| Role | From consolidator label | Behaviour at apply |
|---|---|---|
| **Primary** | `Primary` | The edit that is actually made. Owns the group's outcome. |
| **Subsumed rider** | `Same change` · `Fix mechanism` · `Sub-symptom` | Resolved **automatically** the instant the Primary edit lands. No separate step, not vetoable. |
| **Separable rider** | `Rides along` | A distinct, adjacent edit *enabled by* the Primary and best done in the same job — but **optional and vetoable**. |

The subsumed/separable split is not new vocabulary — it is the existing `consolidator.md:44-53` labels,
read for their apply semantics: three of the four rider labels mean "comes with the Primary," and
`Rides along` means "its own edit."

**Boundaries:**

- **A group is intra-report.** Every member is a rec *in the same report the apply phase operates on*.
  A rider that only exists in another lens's report stays an informational `Related:` cross-ref — never
  a group member, because the apply phase cannot action a rec it does not have. (In a single-lens run,
  cross-lens `Related:` lines point outside the report and are informational only.)
- **Grouping ≠ ordering.** Groups decide *what becomes one job*. Cross-group and standalone-rec
  sequencing is unchanged (dependency order, Critical → Major → Minor). Change #2 replaces only the
  **file-overlap batching**; it does not touch sequencing.

## 3. Decisions (from brainstorm)

1. **Source of truth = the report.** The consolidator declares the group explicitly; the gate and apply
   **read** it. Nothing is re-derived by heuristic. This keeps the report the audit trail.
2. **Rider status vocabulary = reuse `applied`, with a note.** A resolved rider's `Status:` line reads
   `applied (via <primary-id>)`; no new status word is introduced. The **Apply-log line** is what
   disambiguates "resolved for free" from "separately edited" (see §6).
3. **Groups are atomic except for separable riders.** The human approves or rejects a group as a whole.
   The *only* sub-group choice offered is **vetoing a `Rides along` (separable) rider**. Subsumed riders
   are not vetoable — the Primary edit resolves them whether or not you want them, so "excluding" one
   means not making the edit (i.e. rejecting the group). To exclude a finding cleanly, the consolidator
   simply should not have grouped it.
4. **Verification checkpoints Primary first, then each separable.** Run the suite after the
   **Primary + subsumed** edit — green lands the core fix as one unit. Then apply each approved
   **separable** rider and verify it; a separable edit that breaks the suite **reverts alone**, leaving
   the Primary green. Rationale: an optional adjacent cleanup must never sink the core structural fix.
5. **Scope = shared machinery + the umbrella; single-lens degrades gracefully.** The shared gate+apply
   become group-aware and consume a `## Grouped changes` section **when the report has one**. The
   umbrella already emits it, so it benefits immediately. Recs in **no** group apply per-rec exactly as
   today; the file-overlap chain logic is **retained as the fallback** for ungrouped recs and for
   single-lens reports that declare no groups. Teaching single-lens templates to emit groups is a
   possible later item, explicitly out of scope here.

## 4. Phase 3 — group-aware gate

`docs/refactor-workflow.md` Phase 3 (and the umbrella's restatement in `skills/code-quality/SKILL.md`)
present **groups as units**:

- Each group shows its **title + group ID**, its **tier** (= the **Primary's** tier), and its members:
  Primary, subsumed riders (marked *auto — resolve with it*), and separable riders (each offered with a
  *veto?* affordance).
- Approval paths, all still valid:
  - **by tier** — a group is included when its **Primary's** tier matches the approved tier; approving
    pulls the whole group in.
  - **by group** — "apply `group-1`".
  - **by ID** — unchanged for standalone (ungrouped) recs.
- **Vetoing a separable rider** is the sole sub-group choice, offered only on `Rides along` members.
- **Consequence to state in the doc:** a rider only lands **through its Primary**. Approving a Minor
  rider whose Primary is an unapproved Major does **not** apply it — the group is the unit of approval.
- `"None — just the report"` remains a first-class outcome.

## 5. Phase 4 — group = one job

`docs/refactor-workflow.md` Phase 4 + `docs/refactor-agents/implementer.md`:

- **Batching rule changes.** `docs/refactor-workflow.md:135-137`: *"recs touching the same file form a
  chain"* → **"a declared group is one job; ungrouped recs apply per-rec as today."** The file-overlap
  ordering is kept only as the **fallback** for ungrouped/single-lens recs. Cross-group ordering stays
  Critical → Major → Minor.
- **One TDD refactor job per group.** `implementer.md` gains a third apply unit — it already handles
  "one rec *or* one chain"; now **"one group."** The job's `change` = the Primary's proposed change,
  plus the approved separable riders as explicit follow-on steps in the same job.
- **Verification inside the job** (decision §3.4): suite after **Primary + subsumed** (green lands the
  core fix); then each approved **separable** rider applied and verified; a red separable reverts alone,
  Primary stays.

## 6. Status & Apply-log recording

Recorded in the report per the canonical vocabulary (`docs/refactor-workflow.md:176-194`):

| Member | `Status:` line | Apply-log line |
|---|---|---|
| Primary | `applied` \| `failed (reverted)` | `<ts> [<primary>] applied — suite green (N) — diffstat …` |
| Subsumed rider | `applied (via <primary>)` | `<ts> [<rider>] applied — subsumed by <primary> (no separate edit)` |
| Approved separable rider | `applied` \| `failed (reverted)` | `<ts> [<rider>] applied — suite green (N) — diffstat …` (or revert line) |
| Vetoed separable rider | `skipped (not approved)` | — |

The group's outcome is represented by the **Primary's** Status; riders carry their own lines so the
report remains a complete audit trail. `applied (via <primary>)` + the "no separate edit" Apply-log
note together make "resolved for free" unambiguous without a new status word.

## 7. Report-side deltas (what the consolidator must now emit)

Two small additions to the group declaration, authored in `consolidator.md:55-65` and reflected in
`report-template.md:78-94`:

1. **A stable group ID.** Groups have a title but no addressable handle today. Add a short ID (e.g.
   `group-1`) to each `### One edit — …` banner so the gate/apply can reference the group unambiguously.
2. **Split the apply-instruction line.** Today the banner ends *"Apply `clean-arch/major-1`; the rest
   resolve with it"* — true only for subsumed riders. When a group has a `Rides along` member, the
   instruction must distinguish: apply the Primary (subsumed riders resolve with it) **and** apply the
   separable rider(s) as their own step in the same job.

Example of the target banner shape (the real 2026-07-22 `config_sync_fs` group had three
subsumed riders and no separable one; a `Rides along` line is added here **only to illustrate**
the separable rendering):

```markdown
### [group-1] One edit — Extract config_sync_fs.py leaf   [resolves 3 findings across 2 lenses]

- **Primary** · `clean-arch/major-1` — extract the shared fs/path helpers into a leaf module. *Owns the fix.*
- **Same change** · `clean-arch/major-2` — the SDP view of the same edge. *(subsumed — resolves with the Primary)*
- **Fix mechanism** · `solid/major-5` — the DIP inversion that breaks the cycle. *(subsumed)*
- **Sub-symptom** · `clean-arch/minor-2` — the json-namespace reach-through vanishes once the import goes. *(subsumed)*
- **Rides along** · `<illustrative>` — an adjacent cleanup enabled by the extraction. *(separable — its own step; vetoable)*

Apply `clean-arch/major-1` (subsumed riders resolve with it); then apply each `Rides along`
rider as a follow-on step in the same job unless vetoed.
```

## 8. Files touched

| File | Change |
|---|---|
| `docs/refactor-workflow.md` | Phase 3 group-aware approval; Phase 4 "group = one job" replacing file-overlap batching (retained as ungrouped fallback); group verification checkpoints; note that groups are read from the report, never re-derived |
| `docs/refactor-agents/implementer.md` | Third apply unit — "one group": build one TDD job from Primary + subsumed (auto) + approved separable (own steps); per-checkpoint verification; the Status/Apply-log recording in §6 |
| `skills/code-quality/agents/consolidator.md` | Emit the stable group ID and the split apply-instruction (subsumed-auto vs separable-step) when building the Grouped changes section |
| `skills/code-quality/references/report-template.md` | Group ID in the `### One edit` banner; the two-part apply-instruction shape; per-role rider annotation |
| `skills/code-quality/SKILL.md` | Reconcile the **restated** Phase 3/4 prose (`:104-121`, "by tier or ID" / "one queue … suite green after each") so it does not go stale — prefer thinning to a pointer at the shared doc, per the skill's own "Reuse, don't fork" guardrail |

**Not touched:** `skills/ddd/*` and `skills/clean-code/*` apply paths — they are analyze-only
(`docs/refactor-workflow.md:193`), so change #2's apply half does not reach them. Single-lens
`solid` / `gof` / `clean-architecture` report templates are **not** taught to emit groups in this
change; they simply hit the ungrouped fallback (out of scope, §3.5).

## 9. Non-goals / YAGNI

- **No new status vocabulary.** `applied (via …)` reuses `applied` (decision §3.2).
- **No per-rider veto beyond `Rides along`.** Vetoing a subsumed rider is physically incoherent (§3.3).
- **No single-lens group emission.** Deferred; the fallback covers them (§3.5).
- **No parser script.** The report is consumed by the implementer *subagent* (agent-parsed markdown),
  not a regex — reliability comes from explicit structure (group ID + labelled rider roles), not code.
- **No change to sequencing, Risk-based high-risk gating, or the 3-cycle cap** — those stay as-is.

## 10. Verification (of the change itself)

- **Backward compatibility:** a report with **no** `## Grouped changes` section (every single-lens
  report today) must drive the apply phase identically to current behaviour — per-rec jobs, file-overlap
  ordering. This is the primary regression to guard.
- **Structure tests** (siblings of QoL #5, which asserts ID *shape*): assert the group banner carries a
  `group-<n>` ID and that each rider line is annotated subsumed/separable, so a malformed group is caught
  before the gate reads it.
- **Walkthrough on the 2026-07-22 report:** the `config_sync_fs` group (Primary `clean-arch/major-1` +
  three subsumed) approved as one unit → one TDD job → Primary `applied`, three riders
  `applied (via clean-arch/major-1)`, suite green once. Confirms the end-to-end path on real data.
