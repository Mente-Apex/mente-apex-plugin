---
name: clean-architecture
description: >-
  Audit an existing codebase's component and dependency structure through Robert
  C. Martin's Clean Architecture lens — the altitude ABOVE the five SOLID
  principles and orthogonal to DDD's domain modelling. Headline checks (run by
  default) are robust and tool-assisted: the Dependency Rule / boundary audit
  (does core code import the framework, ORM, or DB? is the framework a
  replaceable detail?), import cycles (ADP), and stability direction (SDP).
  Secondary checks (opt-in) cover component cohesion (REP/CCP/CRP), Screaming
  Architecture, and the composition root; an opt-in appendix reports the
  abstractness / Main-Sequence metrics (approximate). Audit-first, no
  build mode — building the layered shape is /ddd's job. Emits a dependency-rule
  contract (import-linter for Python, dependency-cruiser for JS/TS) as a
  leave-behind CI tripwire. Use for "/clean-architecture",
  dependency rule, boundaries, framework as a detail, import cycles, component
  cohesion/coupling, stable dependencies, screaming architecture, composition
  root.
user-invocable: true
metadata:
  version: "0.1.0"
  source: "Robert C. Martin, Clean Architecture (2017), read pragmatically"
---

# clean-architecture — component & dependency-graph audit

The widest zoom in the ladder: not classes (`solid`), not the domain model
(`ddd`), but the **component graph** — deployable/package units and how they
depend on each other. It **audits** existing code; it does **no build** (building
the layered shape is `ddd`'s job). It runs on the shared engine
([../../docs/refactor-workflow.md](../../docs/refactor-workflow.md)) with its own
rubric.

## The carve (why it doesn't fight the others)

- **vs `ddd`:** `ddd` asks *"is the domain modelled well?"*; this asks *"is the
  dependency structure sound, regardless of domain richness?"* Reconcile shared
  smells via [../../docs/lens-overlap.md](../../docs/lens-overlap.md).
- **vs `solid`:** those are the five class-level principles; this is the graph
  topology and their component-scale cousins. Never restate a `solid` DIP finding
  — cross-reference it.
- **vs `clean-code`:** line-level craft is `clean-code`'s; this never touches it.

## Invocation

`/clean-architecture [path] [--cohesion] [--metrics]`

- Default: the **headline** checks only.
- `--cohesion`: also run the **secondary** checks (packaging, Screaming
  Architecture, composition root). May also be offered interactively ("go
  deeper?").
- `--metrics`: also emit the **appendix** (abstractness / Main Sequence).
- Pre-authorizations count as the human review for what they cover.

## Tiers (see [references/principles.md](references/principles.md))

- **Headline (default) — robust, actionable:** Dependency Rule / boundary audit;
  import cycles (ADP); stability direction (SDP).
- **Secondary (opt-in):** component cohesion (REP/CCP/CRP); Screaming
  Architecture; Main Component / composition root.
- **Appendix (opt-in):** abstractness / Main-Sequence metrics — **approximate**
  (see the language reference for the per-language caveat); structural-health
  context, never a finding to refactor toward.

## Tooling posture (tool-assisted, graceful fallback)

Detect a graph tool and use it when present; **degrade to agent-driven import
reading** when not (say which mode ran in the report). The detected language's
`references/<language>.md` names the tools and the how-to: `grimp` +
`import-linter` (`python.md`), `dependency-cruiser` / `madge` (`typescript.md`),
via any available runner (`uvx`, `pipx run`, `npx`, `pnpm dlx`, project-local) —
never a hard install.

## Leave-behind artifact

The Dependency-Rule findings compile to a **dependency-rule contract** in the
detected language's tool (`importlinter.ini` for Python, `.dependency-cruiser.cjs`
for JS/TS) written into the report dir — a one-time audit becomes a repeatable CI
guardrail. Offered for the user to commit; never committed silently.

## Flow (audit-first; apply opt-in)

Follows the shared workflow, Phases 0–3; apply (4–5) is opt-in and conservative.

1. **Phase 0 — Inventory & baseline.** Scope the tree; detect the test suite and a
   graph tool; create git-excluded `docs/reports/clean-architecture/`.
2. **Phase 1 — Analyzer** ([agents/analyzer.md](agents/analyzer.md), read-only) →
   `findings-draft.md`. Headline checks always; secondary/appendix only if opted
   in.
3. **Phase 2 — Reviewer** ([agents/reviewer.md](agents/reviewer.md)) re-verifies
   every finding, tiers Critical/Major/Minor, cross-references the hub, writes
   `docs/reports/clean-architecture/CLEAN-ARCHITECTURE-REPORT-<YYYY-MM-DD>.md` per
   [references/report-template.md](references/report-template.md), and drafts the
   dependency-rule contract.
4. **Phase 3 — Decision gate.** Present the summary. Most CA fixes are large
   (High-risk architectural moves) and stay advisory; **only mechanical, low-risk
   fixes** (break a cycle by moving a class, introduce a boundary port) are opt-in
   appliable via the shared implementer ([agents/implementer.md](agents/implementer.md)).

## Guardrails

- **Audit-first, no build mode.** Never scaffolds a greenfield layered app.
- **Judgment, not dogma.** Honour the when-NOT-to rules in `references/principles.md`:
  don't demand boundaries a single-deployable app hasn't earned; don't chase
  Main-Sequence distance without real multi-component granularity.
- **Defer, don't duplicate.** Cross-reference `solid`/`gof`/`ddd`/`clean-code` via
  the hub; file each shared smell once.
- **The report is the single source of truth**; apply logs live in it.

## File map

- [references/principles.md](references/principles.md) — the tiered rubric,
  violation signatures, when-NOT-to, tier assignment. Both analysis agents read it.
- `references/<language>.md` — graph-tool detection, metric how-to, the
  dependency-rule contract, and graceful degrade for a detected language; ships
  `python.md` and `typescript.md` today (list the `references/` dir for the
  current set). New languages drop in here.
- [references/report-template.md](references/report-template.md) — report format.
- [agents/analyzer.md](agents/analyzer.md), [agents/reviewer.md](agents/reviewer.md),
  [agents/implementer.md](agents/implementer.md) — the three roles.
- [../../docs/refactor-workflow.md](../../docs/refactor-workflow.md) — shared Phase 0–5.
- [../../docs/lens-overlap.md](../../docs/lens-overlap.md) — cross-lens reconciliation.
