# Design — transient `findings-draft.md` lifecycle

**Date:** 2026-07-24
**Status:** approved (design), pending implementation plan
**Touches:** `docs/refactor-workflow.md` (the shared Phase 0–5 orchestration)

## Problem

Every refactor lens (`solid`, `gof`, `clean-architecture`, `test-quality`, the
`code-quality` umbrella, plus the analyze-only `ddd` and `clean-code`) runs a
generator–critic pair over the shared workflow:

1. **Phase 1 — analyzer** (read-only) writes candidate findings to
   `docs/reports/<lens>/findings-draft.md`.
2. **Phase 2 — reviewer** reads that draft, re-verifies every finding against the
   real code, and writes the durable, templated report to
   `docs/reports/<lens>/<LENS>-REPORT-<YYYY-MM-DD>.md`.

`findings-draft.md` is therefore a **transient hand-off** whose sole consumer is the
Phase 2 reviewer. But two asymmetries make it behave as if it were durable:

- The **final report** is written to a **dated** path → it never collides across
  runs.
- The **draft** is written to a **fixed** path (`findings-draft.md`) and is **never
  deleted** by any phase. Phase 0.3 calls reports "ephemeral working artifacts by
  default" but nothing enforces that.

**Observed failure (2026-07-22 → 2026-07-24).** A run on 2026-07-24 tried to write
`findings-draft.md`, but the file from the 2026-07-22 run was still sitting at the
exact fixed path. The Read-before-Write guard correctly blocked the un-read
overwrite. Worse than the block: a fixed-path draft that survives between runs makes
*fresh* and *stale* content indistinguishable, and invites an unsafe Bash-bypass of
the guard that would clobber the prior file with an in-memory blob — leaving a single
file falsely stamped "today" beside genuinely stale siblings.

Root cause, in one line: **the deliverable is dated and durable; the transient
hand-off got a fixed name and no reaper.**

## Goal

Give `findings-draft.md` a lifecycle that matches its nature — written by the
analyzer, consumed by the reviewer, then deleted — so a re-run is never contaminated
by a prior run, without changing what the analyzer or reviewer do.

Non-goals: changing the generator–critic split, changing the draft's format, dating
the draft, or passing findings agent-to-agent in memory (rejected — flaky, and forces
the orchestrator to shuttle a large blob).

## Design

All changes are in the shared `docs/refactor-workflow.md`. Because every lens links
this file rather than restating the phases, all seven lenses inherit the fix with no
per-lens edits. The orchestrator (main agent) owns workspace lifecycle; the analyzer
and reviewer agent docs are unchanged.

### Edit 1 — Phase 2: primary reaper (delete after the report is durable)

After the orchestrator confirms the Phase 2 report **exists and parses** (the fan-in
it already performs under the "artifacts always terminal" guardrail), it **deletes
`docs/reports/<lens>/findings-draft.md`**.

- The draft's only consumer (the reviewer) is finished; from Phase 3 onward the
  **report is the single source of truth** and no phase reads the draft.
- If Phase 5 loops back to a scoped re-analysis, Phase 1 simply writes a fresh draft
  into a now-clean slot — the loop stays collision-free.
- Deletion is conditional on the report being present and parseable: if the reviewer
  died and left no report, the draft is **kept** (it is the only evidence of the
  partial run) and the existing "record the coverage gap loudly" path applies.

### Edit 2 — Phase 0.3: crash-safety pre-clear

When Phase 0.3 creates `docs/reports/<lens>/`, it also **removes any stale
`findings-draft.md`** already present.

- Once Edit 1 exists, the only way a draft survives into a later run is a prior run
  that **crashed** between Phase 1 and end-of-Phase-2 — exactly the 07-22 → 07-24
  case. This pre-clear makes a clean start unconditional.
- It clears only the transient draft, not dated final reports (those are the durable
  record; Phase 0.3 already leaves them alone).

### Edit 3 — one lifecycle sentence

Near the cast table / guardrails, state the draft's lifecycle explicitly so future
edits don't silently reintroduce a persistent draft:

> `findings-draft.md` is transient: **written** by the analyzer (Phase 1),
> **consumed** by the reviewer (Phase 2), **deleted** by the orchestrator once the
> report is durable (end of Phase 2). Only the dated report persists.

## Rejected alternatives

- **Date the draft** (`findings-draft-<date>.md`): no collision, but drafts
  accumulate forever — contradicts "transient."
- **Memory-to-memory hand-off**: flaky; forces the orchestrator to shuttle a large
  findings blob between subagents.
- **Read-then-overwrite inside the analyzer**: the Bash-bypass instinct in disguise;
  makes the analyzer ingest a stale artifact it should not care about, and still
  leaves fresh/stale ambiguity on a half-completed write.

## Scope & impact

- **One file changes:** `docs/refactor-workflow.md` (Phase 0.3, Phase 2, plus the
  lifecycle note). No agent-doc or per-lens SKILL edits.
- **Umbrella safe:** `code-quality` merges the final per-lens **reports**, never
  `findings-draft.md`, so per-lens deletion after Phase 2 does not starve it.
- **Analyze-only lenses safe:** `ddd` and `clean-code` stop after Phase 3 but still
  run Phases 1–2, so the same lifecycle (delete after Phase 2) applies uniformly.

## Verification

The change is to orchestration prose, so verification is behavioral, exercised on a
real lens run:

1. **Clean re-run:** run a lens twice in a row on the same target. Second run's Phase
   1 must succeed with no Read-before-Write block, and after Phase 2 the lens's
   `findings-draft.md` must be **absent** while the dated report is present.
2. **Crash-safety:** leave a stale `findings-draft.md` in place (simulating a crashed
   prior run), start a new run, and confirm Phase 0.3 clears it before Phase 1 writes.
3. **Reviewer-failure keeps the draft:** if Phase 2 produces no parseable report, the
   draft is retained and the coverage gap is reported — deletion must not fire on a
   missing report.
