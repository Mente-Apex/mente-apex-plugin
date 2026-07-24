# Refactor-Workflow Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close four orchestration gaps in the plugin's shared refactor workflow so subagents and the apply phase can't be tripped up by stale or ambiguous state.

**Architecture:** These are **Markdown orchestration edits**, not code — the plugin's behavior lives in skill/agent instruction files that the main agent and its subagents read at runtime. There is no compiler or unit-test suite for this layer, so each task's verification is (a) a `grep`/read assertion that the new instruction landed, (b) an internal-consistency check that cross-references resolve, and (c) the behavioral scenario from the spec, described for a human/agent to walk. Each concern is an independent, separately-reviewable unit and gets its own task + commit.

**Tech Stack:** Markdown; `git`; `rg`/`grep` for verification. No runtime, no build.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-24-refactor-workflow-hardening-design.md` — the authority; every task traces to a C1–C4 section there.
- **Branch:** all work lands on `fix/transient-findings-draft-lifecycle` (already checked out). Do **not** create a new branch.
- **No code, no rubric changes.** Only orchestration/agent instruction docs change. No edits to lens rubrics, the TDD apply-engine contract, or the analyzer/reviewer role split.
- **Verbatim vocabulary (must match exactly across tasks):**
  - conflict section heading: `## Conflicts`; entry id form: `conflict-<n>`; loser status string: `skipped (lost conflict to <winner-id>)`.
  - shared index third artifact name: **symbol index**; build chain: `ast-grep` → `ctags` → agent-read.
  - draft lifecycle verb sequence: written (P1) → consumed (P2) → deleted (end P2).
- **Commit style:** Conventional Commits, one commit per task, ending with the repo's `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.
- **Anchor by heading/quoted phrase, not line number** — these files will drift as tasks land; locate each edit by the `grep` anchor given, not by the line numbers in the spec.

---

### Task 1 (C1): Transient `findings-draft.md` lifecycle

**Files:**
- Modify: `docs/refactor-workflow.md` — Phase 0.3 (anchor: `Report dir`), Phase 2 (anchor: `## Phase 2 — Reviewer`), cast table (anchor: `**The cast**`).

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: the lifecycle vocabulary (`written (P1) → consumed (P2) → deleted (end P2)`) that Task 4's "analysis-only" boundary refers back to.

- [ ] **Step 1: Confirm the gap exists (would-fail check)**

Run: `rg -n "delete.*findings-draft|pre-clear|reap the draft" docs/refactor-workflow.md`
Expected: no matches (the reaper does not exist yet).

- [ ] **Step 2: Add the Phase 0.3 pre-clear**

In `docs/refactor-workflow.md`, in Phase 0's numbered item **3. Report dir** (the paragraph ending "…commit a final report as a living doc at the end."), append:

```markdown
   - **Pre-clear a stale draft.** A `findings-draft.md` is a transient
     analyzer→reviewer hand-off, never a durable record, so a copy left in the
     report dir can only be stale — from a prior run that crashed between Phase 1
     and the end of Phase 2. Delete any pre-existing
     `docs/reports/<lens>/findings-draft.md` now, before Phase 1 writes. Dated
     final reports are the durable record and are left untouched.
```

- [ ] **Step 3: Add the Phase 2 reaper**

In `docs/refactor-workflow.md`, at the end of the `## Phase 2 — Reviewer` section (after the sentence ending "…the apply phase depends on its structure (IDs, Risk and Status fields)."), append a new paragraph:

```markdown
**Reap the draft.** Once you have confirmed the report exists and parses (the
fan-in in Guardrails), delete `docs/reports/<lens>/findings-draft.md` — its only
consumer is the reviewer, and from Phase 3 on the dated report is the single
source of truth. **Delete only against a parseable report:** if the reviewer
produced none (it died), keep the draft as the sole evidence of the partial run
and record the coverage gap per the "artifacts always terminal" guardrail — never
delete a draft you cannot replace with a report.
```

- [ ] **Step 4: Add the lifecycle note after the cast table**

In `docs/refactor-workflow.md`, immediately after the cast table paragraph (which ends "…The role separation is what keeps false positives out of the report — don't collapse it."), add:

```markdown
**The draft is transient.** `findings-draft.md` is the analyzer→reviewer
hand-off, not a deliverable: **written** by the analyzer (Phase 1), **consumed**
by the reviewer (Phase 2), **deleted** by the orchestrator once the report is
durable (end of Phase 2). Only the dated `<LENS>-REPORT-<YYYY-MM-DD>.md`
persists. An edit that leaves the draft on disk between runs reintroduces the
stale-collision bug this rule exists to prevent.
```

- [ ] **Step 5: Verify the three edits landed and are consistent**

Run: `rg -n "Pre-clear a stale draft|Reap the draft|The draft is transient" docs/refactor-workflow.md`
Expected: exactly three matches (one per edit).
Read the three edits in context and confirm: the reaper is conditional on a parseable report, and the pre-clear only removes the draft (not dated reports).

- [ ] **Step 6: Behavioral walk (from spec C1 verification)**

Confirm by reading, not running: a second lens run on the same target now has (a) Phase 0.3 clearing any leftover draft before Phase 1, and (b) Phase 2 deleting the draft after the report is durable — so the fixed-path collision that blocked the 07-22→07-24 run cannot recur, while a reviewer-death still keeps the draft.

- [ ] **Step 7: Commit**

```bash
git add docs/refactor-workflow.md
git commit -m "fix(refactor-workflow): give findings-draft.md a transient lifecycle

Delete the analyzer->reviewer draft after Phase 2 once the report is durable
(kept if the reviewer left no parseable report), pre-clear a crashed run's
stale draft in Phase 0.3, and document the written->consumed->deleted
lifecycle so it can't silently regress.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2 (C2): Phase-0 shared symbol index

**Files:**
- Modify: `skills/code-quality/SKILL.md` — Phase 0 (anchor: `Build the shared index here`), Phase 1 (anchor: `search narrowly, not sweep`).

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: the **symbol index** artifact and the "shared index is an analysis-phase artifact" marker that Task 4 (C4) relies on to state the apply-phase boundary.

- [ ] **Step 1: Confirm the gap (would-fail check)**

Run: `rg -n "symbol index" skills/code-quality/SKILL.md`
Expected: no matches (only file list + import graph exist today).

- [ ] **Step 2: Add the symbol index to the Phase-0 shared-index build**

In `skills/code-quality/SKILL.md`, in the Phase 0 paragraph beginning "**Build the shared index here, once**", after the sentence ending "…build it here and share rather than have each lens re-derive imports by grep." insert:

```markdown
Build a **third artifact next to the file list and import graph: a symbol
index** — every class / function / method definition with its `file:line`, name,
and rough LOC — **once**, with a real tool when reachable and degrading exactly
as the import graph does: **`ast-grep`** (primary; already used in Phase 1 for
structural queries) → **`ctags`** (fallback) → **agent-read of the scoped file
list** (last resort, recorded as a coverage note). Six analyzers each
re-enumerating the tree's classes, functions, and call-sites is the same waste
the import graph already removes for edges. This shared index is an
**analysis-phase artifact** — built once over Phases 0–2's single read-only
snapshot; it must **not** be consumed by the apply phase, which mutates the tree
(see the implementer's re-derive rule).
```

- [ ] **Step 3: Generalize the Phase-1 "search narrowly" instruction to symbols**

In `skills/code-quality/SKILL.md`, in the Phase 1 paragraph beginning "Tell each analyzer to **search narrowly, not sweep**", after the clause "answer import questions from the shared graph (never by grepping `import` lines);" insert:

```markdown
answer **definitional** questions — where classes/functions/methods are defined,
their names, their call-sites — **from the shared symbol index, never by
re-enumerating the tree** (the same rule as imports; the index is built once in
Phase 0). A lens's remaining *semantic* search (SOLID's discriminator
conditionals, GoF's global-state sites) still runs, but scoped to the Phase-0
file list against that pre-built corpus, not as a fresh full-tree sweep;
```

- [ ] **Step 4: Verify edits landed and vocabulary matches the global constraint**

Run: `rg -n "symbol index|ast-grep.*ctags|analysis-phase artifact" skills/code-quality/SKILL.md`
Expected: matches for the symbol index build, the `ast-grep`→`ctags` chain, and the analysis-phase marker.
Confirm the build chain reads `ast-grep` → `ctags` → agent-read (matches Global Constraints exactly).

- [ ] **Step 5: Behavioral walk (from spec C2 verification)**

Confirm by reading: on `/code-quality`, Phase 0 now produces a symbol index in `docs/reports/code-quality/`, and the Phase-1 brief routes definitional lookups to it — so no analyzer re-enumerates definitions the index already holds; the agent-read degrade path is recorded when no tool is reachable.

- [ ] **Step 6: Commit**

```bash
git add skills/code-quality/SKILL.md
git commit -m "feat(code-quality): pre-collect a shared symbol index in Phase 0

Extend the umbrella's shared index (file list + import graph) with a symbol
index built once (ast-grep -> ctags -> agent-read) so the six analyzers answer
definitions and call-sites from it instead of each re-grepping the tree, the
same way imports are already answered from the shared graph. Mark the index an
analysis-phase artifact — not for the mutating apply phase.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3 (C3): Conflict/exclusion resolution at the decision gate

**Files:**
- Modify: `skills/code-quality/agents/consolidator.md` (anchor: `Surface tensions, don't resolve them`).
- Modify: `skills/code-quality/references/report-template.md` (anchor: `Unresolved tensions`).
- Modify: `docs/refactor-workflow.md` — Phase 3 (anchor: `## Phase 3 — Decision gate`) and Phase 4 (anchor: `## Phase 4 — Apply via TDD`).
- Modify: `skills/code-quality/SKILL.md` — Phase 3 (anchor: `Unresolved tensions`).

**Interfaces:**
- Consumes: nothing structural from Tasks 1–2.
- Produces: the `## Conflicts` block, `conflict-<n>` id form, and `skipped (lost conflict to <winner-id>)` status — all consumed by the shared Phase 3 gate and Phase 4 refusal below. These strings must match Global Constraints verbatim.

- [ ] **Step 1: Confirm the gap (would-fail check)**

Run: `rg -n "## Conflicts|lost conflict to|mutually.exclusive" docs/refactor-workflow.md skills/code-quality/`
Expected: no matches (the gate models cohesion via `## Grouped changes` but has no exclusion construct).

- [ ] **Step 2: Strengthen consolidator rule 7 to emit a structured `## Conflicts` block**

In `skills/code-quality/agents/consolidator.md`, replace rule **7** (the paragraph beginning "7. **Surface tensions, don't resolve them.**") with:

```markdown
7. **Surface tensions and forks — structurally, don't resolve them.** Two cases.
   A *soft tension* (the hub's Singleton ↔ DIP — two philosophies, both livable)
   goes under **Unresolved tensions** as today. A **hard conflict** — two
   actionable recs that are **mutually exclusive**, where applying one voids the
   other (`apply A ⟹ ¬apply B`) — is stronger: emit a **`## Conflicts`** block
   parallel to `## Grouped changes`, one `### [conflict-<n>]` entry per fork with
   the rec IDs, the **axis of disagreement**, and the **consequence**
   (`apply solid/med-2 ⟹ drop ddd/med-1`). Give each a stable id (`conflict-1`,
   …) so the gate can address it. Do **not** pick a winner — the human decides at
   the gate. A fork is **not** a group: never fold mutually-exclusive recs into a
   `## Grouped changes` entry.
```

- [ ] **Step 3: Add the `## Conflicts` section to the report template**

In `skills/code-quality/references/report-template.md`, immediately **before** the `## Cross-lens notes` heading, insert:

```markdown
## Conflicts

Mutually-exclusive recs — applying one voids the other. The gate resolves each
before the apply order is computed; blanket/tier approval cannot resolve a fork.
Omit this whole section if there are no hard conflicts.

### [conflict-1] <one-line axis of disagreement>
- **Recs:** <id-A> vs <id-B>
- **Disagree about:** <the axis — e.g. "repository owns the query cache" vs "cache belongs in the service layer">
- **Consequence:** apply <id-A> ⟹ drop <id-B> (and vice versa)
- **Resolution:** <filled at the gate: winner id, or "neither">

```

- [ ] **Step 4: Make the shared Phase 3 resolve conflicts before ordering**

In `docs/refactor-workflow.md`, in `## Phase 3 — Decision gate (human)`, after the paragraph beginning "Read the final report and present a compact summary…" insert:

```markdown
**Resolve conflicts before computing the apply order.** If the report has a
`## Conflicts` section, each entry is a **fork** — two mutually-exclusive recs
where applying one voids the other. Resolve **every** conflict here, before any
ordering, with an explicit either/or (AskUserQuestion: pick the winner, or
"neither"). A mutual exclusion is a *branch, not a dependency* — the
dependency-aware apply order cannot be linearized while both sides are approved,
so resolution is upstream of Phase 4, not inside it. **Tier/blanket approval
cannot resolve a fork:** "apply all Major" is undefined over a mutually-exclusive
pair — intercept and force the pick **even under a pre-authorization** (a pre-auth
covers independent recs; a fork has no "all" answer). Record the loser's
`Status:` as `skipped (lost conflict to <winner-id>)` — not a bare
`skipped (not approved)` — so a later reader sees *why* it was excluded and does
not resurrect it. **Checklist: every declared conflict is resolved before the
apply order is computed.**
```

- [ ] **Step 5: Add the Phase 4 apply-time refusal (belt-and-suspenders)**

In `docs/refactor-workflow.md`, at the end of the `## Phase 4 — Apply via TDD` intro (before the "**Working branch first.**" paragraph, or immediately after it), add:

```markdown
**A conflict must never reach here unresolved.** If a `## Conflicts` entry
somehow arrives at apply with no gate resolution, **halt and return to Phase 3** —
the implementer never picks a conflict's winner itself. (Phase 3's checklist
exists to prevent this; this is the backstop.)
```

- [ ] **Step 6: Point the umbrella's Phase 3 at the resolution step**

In `skills/code-quality/SKILL.md`, in `### Phase 3 — Decision gate`, in the sentence that currently mentions "*Unresolved tensions* the consolidator surfaced (e.g. Singleton ↔ DIP)", append:

```markdown
 Resolve every `## Conflicts` **fork** per the shared Phase 3 (an explicit
either/or, before ordering, un-satisfiable by tier/blanket approval) — this is
distinct from the softer *Unresolved tensions*, which you merely present.
```

- [ ] **Step 7: Verify all five edits landed and the vocabulary is consistent**

Run: `rg -n "## Conflicts|conflict-<n>|lost conflict to <winner-id>|A fork is \*\*not\*\* a group|halt and return to Phase 3" docs/refactor-workflow.md skills/code-quality/`
Expected: the `## Conflicts` heading appears in the template; the `conflict-<n>` id form appears in the consolidator; the exact loser-status string appears in Phase 3; the Phase 4 refusal appears. Confirm the loser-status string matches Global Constraints character-for-character.

- [ ] **Step 8: Behavioral walk (from spec C3 verification)**

Confirm by reading: given a report with a `## Conflicts` entry under a blanket "apply all Med" pre-authorization, the gate still stops and forces the either/or; the loser lands `skipped (lost conflict to <id>)`; the apply order is computed only over the reduced set; and a conflict reaching Phase 4 unresolved makes apply halt rather than choose.

- [ ] **Step 9: Commit**

```bash
git add docs/refactor-workflow.md skills/code-quality/agents/consolidator.md skills/code-quality/references/report-template.md skills/code-quality/SKILL.md
git commit -m "feat(refactor-workflow): resolve mutually-exclusive recs at the gate

The gate modeled cohesion (grouped changes) but not exclusion, so tier approval
pulled in both sides of a fork and the conflict only bit at apply time. Add a
structured ## Conflicts block (consolidator + report template) and resolve every
fork at the shared Phase 3 before the apply order is computed — un-satisfiable by
blanket approval, loser recorded as 'skipped (lost conflict to <id>)', with a
Phase 4 backstop that halts rather than choosing.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4 (C4): Apply phase re-derives structure fresh

**Files:**
- Modify: `docs/refactor-agents/implementer.md` — Inputs (anchor: `## Inputs (from the orchestrator)`) and per-unit loop step 1 (anchor: `## Per-unit loop`).
- Modify: `docs/refactor-workflow.md` — Phase 4 (anchor: `## Phase 4 — Apply via TDD`).
- Verify only (no new edit): `skills/code-quality/SKILL.md` already carries the "analysis-phase artifact / must not be consumed by apply" marker from Task 2.

**Interfaces:**
- Consumes: the "shared index is an analysis-phase artifact" marker produced by Task 2, and the `## Conflicts`/drift-stop vocabulary from Task 3 (a drifted rec "may be moot or now conflicts").
- Produces: nothing later tasks depend on (final task).

- [ ] **Step 1: Confirm the gap (would-fail check)**

Run: `rg -n "re-derive|drifted|analysis-time snapshot|live tree" docs/refactor-agents/implementer.md`
Expected: no matches (the implementer trusts the report's citations today).

- [ ] **Step 2: Add the re-derive step to the implementer's per-unit loop**

In `docs/refactor-agents/implementer.md`, in `## Per-unit loop`, insert a new numbered step **before** the current step 1 ("Read the unit and every file it cites…"), renumbering the rest:

```markdown
1. **Re-derive against the live tree first.** The report's `file:line` citations
   are an *analysis-time snapshot*. By the time your job runs, earlier approved
   jobs have applied and checkpoint-committed, so those citations have **drifted**
   — and an earlier rec may already have moved or split the class you target.
   Before building `targets`, re-grep/re-read the **current** tree to resolve the
   rec's symbols and locations as they are **now** — scoped to the rec's targets
   and their importers, not a full-repo sweep, and re-derived **per job** (a
   single re-index at apply-start goes stale after the first checkpoint). **Never**
   locate targets from the Phase-0 shared index — that is a pre-refactor snapshot,
   an analysis-phase artifact. If a cited target has drifted away, or an earlier
   rec already changed the structure this rec assumed, **stop and surface it**:
   the rec may be moot or now conflicts — mark it `skipped` with a one-line reason
   and hand it back, rather than editing a stale citation.
```

- [ ] **Step 3: Note in Inputs that the shared index is not an apply input**

In `docs/refactor-agents/implementer.md`, at the end of `## Inputs (from the orchestrator)`, add a bullet:

```markdown
- **Not** the Phase-0 shared index (file list / import graph / symbol index) — it
  is an analysis-phase snapshot of a tree the apply phase has since mutated. You
  re-derive structure fresh against the live tree (per the per-unit loop), never
  from that index.
```

- [ ] **Step 4: State the boundary in Phase 4 of the shared workflow**

In `docs/refactor-workflow.md`, in `## Phase 4 — Apply via TDD`, add near the top (after the conflict-backstop paragraph added in Task 3):

```markdown
**The Phase-0 shared index is analysis-only.** It was built once over the
read-only analysis snapshot; the apply phase mutates the tree via checkpoint
commits, so each implementer re-derives structural facts **fresh, per job**
against the live tree — never from that index. See
[docs/refactor-agents/implementer.md](refactor-agents/implementer.md).
```

- [ ] **Step 5: Verify edits landed and the cross-reference resolves**

Run: `rg -n "Re-derive against the live tree|analysis-only|Not.*Phase-0 shared index" docs/refactor-agents/implementer.md docs/refactor-workflow.md`
Expected: the re-derive step in `implementer.md`, the Inputs exclusion bullet, and the Phase-4 "analysis-only" boundary.
Confirm the Phase-4 link path `refactor-agents/implementer.md` is correct relative to `docs/refactor-workflow.md` (both under `docs/`).

- [ ] **Step 6: Behavioral walk (from spec C4 verification)**

Confirm by reading: with two queued recs where the first moves/splits a class the second cites, the second job re-derives against the live tree, finds the cited target drifted, and stops-and-surfaces rather than editing stale structure — and the implementer never reads the Phase-0 index at apply time.

- [ ] **Step 7: Commit**

```bash
git add docs/refactor-agents/implementer.md docs/refactor-workflow.md
git commit -m "fix(refactor-workflow): apply phase re-derives structure fresh per job

The shared Phase-0 index is an analysis-time snapshot; the apply phase mutates
the tree via checkpoint commits, so the implementer must re-derive the rec's
symbols/locations against the live tree per job (scoped to targets + importers),
never from the index or the report's drifted citations. A cited target that has
drifted away, or a structure an earlier rec already changed, is stopped and
surfaced rather than edited blindly.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification (after all four tasks)

- [ ] **All new vocabulary is internally consistent across files**

Run: `rg -n "findings-draft|symbol index|## Conflicts|lost conflict to|re-derive|analysis-phase artifact|analysis-only" docs/refactor-workflow.md docs/refactor-agents/implementer.md skills/code-quality/`
Expected: C1 lifecycle terms in the workflow; `symbol index` in the umbrella; `## Conflicts` in template + consolidator + both Phase 3s; the loser-status string once in Phase 3; `re-derive`/`analysis-only` in implementer + Phase 4.

- [ ] **Spec coverage** — reread `docs/superpowers/specs/2026-07-24-refactor-workflow-hardening-design.md` and confirm every C1–C4 "Design" bullet maps to a landed edit; list any gap and add a follow-up task if found.

- [ ] **Git log** — `git log --oneline c7d81f4..HEAD` shows the two design commits plus four implementation commits (one per task).
