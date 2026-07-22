# Consolidated report template

The consolidator writes `docs/reports/code-quality/CODE-QUALITY-<YYYY-MM-DD>.md`
in exactly this shape. Like every lens report it is **load-bearing**: the shared
decision gate parses tiers and Risk fields to build the approval question, and
the shared implementer updates Status and the Apply log in place
([../../../docs/refactor-workflow.md](../../../docs/refactor-workflow.md) Phases 3–5).
Keep the field names verbatim.

## IDs

Every merged finding keeps its **origin**: the ID is `<LENS>-<origID>` where
`<LENS>` ∈ `CA | DDD | SOLID | GOF | CC` and `<origID>` is the rec ID the owning
lens assigned in its own report (`C1`, `M2`, `N3`, …). So `SOLID-C1`, `CA-M2`,
`GOF-C1`. This is what lets a reader open the owning lens's full report for the
long-form evidence, and lets the implementer apply a rec with the fix idiom its
lens intended. IDs are permanent; later cycles append, never renumber.

## Shape

```markdown
# Code Quality — <project name> — <YYYY-MM-DD>

## Summary

- Scope: <path analyzed>, <N> source files, <languages>
- Test suite: <command> — <green / N failing at baseline / none found>
- Lenses run: clean-architecture, ddd (analyze), solid, gof, clean-code
  <note any that degraded or found nothing, e.g. "gof — no findings">
- Findings after dedup: <n> Critical, <n> Major, <n> Minor  (<k> overlaps merged)
- Top wins: <the 3–5 recs a human should care about most across all lenses, one line each>

## Recommendations

### Critical

#### [SOLID-C1] <short imperative title>

- **Lens:** SOLID — <SRP | OCP | LSP | ISP | DIP>   <!-- the owning lens + its rubric hook -->
- **Location:** `path/to/file.py:120-310` <all affected sites>
- **Evidence:** <2–4 sentences, quoting the key lines — carried from the lens report>
- **Reader impact:** <why this hurts a human trying to understand or change the code>
- **Proposed change:** <concrete, behavior-preserving steps>
- **Risk:** <Low | Medium | High> — <what could break>
- **Also seen by:** <other lens + rec ID, or "—">   <!-- populated for merged overlaps -->
- **Full detail:** `docs/reports/solid/SOLID-REFACTOR-<date>.md#solid-c1`
- **Status:** pending

### Major

#### [CA-M1] ...

### Minor

#### [CC-N1] ...

## Cross-lens reconciliation

One row per overlap that was merged (per [../../../docs/lens-overlap.md](../../../docs/lens-overlap.md)):

| Shared smell | Filed as | Also flagged by | Resolution |
|---|---|---|---|
| duplicated type-switch on payment kind | SOLID-C1 (OCP) | GOF-C2 (Strategy) | one change; GoF Strategy is the fix idiom, filed under SOLID |
| use-case imports the web framework | CA-C1 (dependency rule) | DDD-M3 (missing port), SOLID-M1 (DIP) | one change; filed at component altitude under CA |

**Unresolved tensions** (surfaced, not auto-decided): <e.g. "Singleton (GOF) vs
DIP (SOLID) on `Config` — the lenses disagree; decide at the gate", or "none">.

## Coverage & method

- Per lens: which ran, tool-assisted vs agent-driven (clean-architecture), any
  areas skipped, any lens that errored (recorded as a coverage gap, never silent).
- Baseline: <suite status before any change>

## Apply log

<!-- Appended by the implementer, one line per attempt, exactly as in the lens templates: -->
<!-- <UTC timestamp> [SOLID-C1] applied — suite green (42 passed) — diffstat: 3 files, +120/-85 -->
```

Status values: `pending` → `applied` | `failed (reverted)` | `skipped (not
approved)` — identical to the lens templates, so the shared implementer needs no
special casing.
