---
name: code-quality
description: >-
  The umbrella full-audit for a codebase's quality — runs all five review lenses
  in one pass and merges them into a single, deduplicated Critical/Major/Minor
  report. It fans out clean-architecture (component/dependency graph), ddd
  (domain model, analyze-only), solid (the five class principles), gof (design
  patterns), and clean-code (line-level craft), reconciles their overlaps via the
  shared hub so a smell seen by two lenses is filed once, then hands the merged
  report to the same human decision-gate and TDD apply engine every lens uses.
  Use for "/code-quality", "full code-quality audit", "run all the quality
  lenses", "everything — SOLID, patterns, architecture, clean code", "how healthy
  is the architecture of this codebase", or any request for a comprehensive,
  multi-lens structural/craft assessment rather than one specific lens. When the
  user names a single lens ("just SOLID", "check the dependency graph"), defer to
  that lens's own skill instead — this is the all-at-once entry point. This is NOT
  a diff/PR bug review: for correctness findings on a change set that belongs to
  /code-review; /code-quality is the whole-codebase architecture-and-craft audit
  (design principles, patterns, dependency structure, domain model, line craft).
user-invocable: true
metadata:
  version: "0.1.0"
---

# code-quality — the five-lens umbrella audit

The plugin has five code-quality lenses, each sound on its own and each still
invokable on its own (`/clean-architecture`, `/ddd analyze`, `/solid`, `/gof`,
`/clean-code`). This skill is the **all-at-once entry point**: it runs every lens
over the same target and returns **one consolidated report** instead of five you'd
have to cross-read yourself. Its value is not new analysis — it is *orchestration
and reconciliation*: scope the tree once, fan the lenses out in parallel, and merge
their findings so a smell two lenses both see (a type-switch that is OCP *and*
Strategy; a boundary violation that is the Dependency Rule *and* a missing port)
lands in the report **once**, at the right altitude, with the others cross-referenced.

**It reuses the shared engine end to end** —
[../../docs/refactor-workflow.md](../../docs/refactor-workflow.md) (Phases 0, 3, 4,
5) and [../../docs/lens-overlap.md](../../docs/lens-overlap.md) (the reconciliation
hub). It adds exactly two things of its own: a parallel fan-out over the five
lenses' analysis passes, and a **consolidation** step that dedups them. Everything
downstream of the merged report — the human gate, the TDD apply, the final
verification — is the shared flow, unchanged.

## Invocation

`/code-quality [path] [--cohesion] [--metrics]`

- `path` scopes the audit (default: repo root).
- `--cohesion` / `--metrics` pass straight through to `clean-architecture` (its
  secondary checks / Main-Sequence appendix); ignored by the other lenses.
- Pre-authorizations count as the human review for whatever they cover
  ("audit only", "apply everything Critical") — don't re-ask. This makes the
  umbrella usable non-interactively.

## Flow

### Phase 0 — Inventory & baseline (once, shared)

Run [../../docs/refactor-workflow.md](../../docs/refactor-workflow.md) **Phase 0
yourself, a single time**: scope the tree, detect and run the test suite once to
establish the baseline, and create the git-excluded report dirs. This is the whole
point of an umbrella — the five lenses would otherwise each re-scan the tree and
re-run the suite. Create `docs/reports/code-quality/` **plus** each lens's own
`docs/reports/<lens>/` (the lenses write there; the consolidator reads from there).

### Phase 1 — Fan out the five analyzers (parallel)

Dispatch **five analyzer subagents at once** (Agent tool, `general-purpose`,
read-only), one per lens. Give each the Phase-0 scope notes and test command so it
doesn't redo them, and tell it to read its lens's analyzer instructions:

| Lens | Analyzer reads | Mode passed |
|---|---|---|
| clean-architecture | `skills/clean-architecture/agents/analyzer.md` | headline checks; add secondary/appendix only if `--cohesion`/`--metrics` |
| ddd | `skills/ddd/agents/analyzer.md` | **analyze mode only** — never design/build |
| solid | `skills/solid/agents/analyzer.md` | — |
| gof | `skills/gof/agents/analyzer.md` | — |
| clean-code | `skills/clean-code/agents/analyzer.md` | **deep gear** (two-stage, writes a report — not the inline quick gear) |

Each writes its `docs/reports/<lens>/findings-draft.md`. Collect all five before
the next wave; a lens that errors is a recorded coverage gap, not a blocker.

### Phase 2 — Fan out the five reviewers (parallel)

Dispatch **five reviewer subagents**, one per lens (`skills/<lens>/agents/reviewer.md`),
each given only its own lens's draft. They run their normal verified pass and write
their lens's own report (e.g. `docs/reports/solid/SOLID-REFACTOR-<date>.md`). They
need **not** cross-reference each other here — because dedup is deferred to the
consolidator, the five reviewers are independent and run concurrently. (If a
reviewer cross-references the hub out of habit, that's harmless; the consolidator is
authoritative.)

### Phase 2.5 — Consolidate (the umbrella's own step)

Dispatch **one consolidator subagent** reading
[agents/consolidator.md](agents/consolidator.md). Tell it which lens reports exist
(name the absent ones explicitly). It merges the five reports into
`docs/reports/code-quality/CODE-QUALITY-<YYYY-MM-DD>.md` per
[references/report-template.md](references/report-template.md), filing each shared
smell once at the owning altitude and cross-referencing the rest. Read the merged
report yourself before the gate.

### Phase 3 — Decision gate (human, shared)

Follow the shared workflow's Phase 3 on the **consolidated** report: present counts
by tier, the top wins across all lenses, anything High-risk, and any *Unresolved
tensions* the consolidator surfaced (e.g. Singleton ↔ DIP). Ask which recs to apply
by tier or ID — unless pre-authorized. **"None — just the report" is a first-class
outcome**; stop there gracefully. Since the merged report carries each lens's
original rec IDs, Risk, and Status fields verbatim, no lens-specific handling is
needed here.

### Phases 4–5 — Apply via TDD & final review (shared, opt-in)

Approved recs apply through the **unchanged** shared Phase 4/5 (the TDD refactor
engine). Each merged finding keeps its lens origin, so the implementer applies it
with the fix idiom that lens intended. One working branch (`code-quality/<slug>`),
one queue ordered Critical → Major → Minor, suite green after each — exactly as a
single lens would, just spanning all five. Then verify the suite yourself and offer
to commit/PR via `/ship`; never auto-publish.

## Guardrails

- **No new analysis of your own.** The umbrella orchestrates and reconciles; every
  finding traces to a lens reviewer that verified it. If you spot something the
  lenses missed, it goes in the report's Coverage notes, not into the diff.
- **Absence is data, never silence.** A lens that errors or finds nothing is
  recorded in the consolidated report's Coverage section. A missing report can then
  only mean an agent died — say so loudly and proceed; a silent hole is worse.
- **Reuse, don't fork.** The gate, the apply engine, the report field semantics,
  and the overlap hub are shared. This skill adds fan-out + consolidation and
  nothing else; if you find yourself restating a lens's rubric or the apply
  mechanics, stop — link the shared doc instead.
- **Each lens still stands alone.** Nothing here changes the five skills; a user who
  wants only one runs it directly. This is the convenience layer on top, not a
  replacement.
- **Judgment, not dogma.** A full audit can surface a lot; the top-wins summary
  exists so the human isn't buried. Volume is not value — the goal is the handful of
  changes that most improve a human reader's comprehension.

## File map

- [references/report-template.md](references/report-template.md) — the consolidated
  report format (the only report the umbrella emits directly).
- [agents/consolidator.md](agents/consolidator.md) — the merge/dedup role.
- [../../docs/refactor-workflow.md](../../docs/refactor-workflow.md) — the shared
  Phase 0/3/4/5 this skill reuses verbatim.
- [../../docs/lens-overlap.md](../../docs/lens-overlap.md) — the reconciliation hub.
- The five lenses: [../clean-architecture/SKILL.md](../clean-architecture/SKILL.md),
  [../ddd/SKILL.md](../ddd/SKILL.md), [../solid/SKILL.md](../solid/SKILL.md),
  [../gof/SKILL.md](../gof/SKILL.md), [../clean-code/SKILL.md](../clean-code/SKILL.md).
