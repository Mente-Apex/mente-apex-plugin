# Consolidated report template

The consolidator writes `docs/reports/code-quality/CODE-QUALITY-<YYYY-MM-DD>.md`
in exactly this shape. Like every lens report it is **load-bearing**: the shared
decision gate parses tiers and Risk fields to build the approval question, and
the shared implementer updates Status and the Apply log in place
([../../../docs/refactor-workflow.md](../../../docs/refactor-workflow.md) Phases 3–5).
Keep the field names verbatim.

## IDs

Each lens already assigns a **globally-unique, self-describing** rec ID —
`<lens>/<tier>-<n>` — so the consolidator **carries it verbatim** and never
re-prefixes. `<lens>` ∈ `clean-arch | ddd | solid | gof | clean-code | test-quality`;
`<tier>` ∈ `critical | major | minor` for **all six** lenses (clean-code and test-quality
grade on the same three tiers — see their standards' Severity rubrics — so nothing needs
translating). So `solid/major-5`, `clean-arch/critical-1`, `test-quality/major-2` —
from the code alone a reader knows the owning lens and the tier, and can open that
lens's own report for the long-form evidence without decoding a legend. IDs are
permanent; later cycles append, never renumber.

Because the lens prefix already disambiguates, two lenses can both have a
`major-1`; the prefix (`solid/major-1` vs `ddd/major-1`) keeps them distinct.

## Legend (emit this verbatim into every report)

The report must be decodable without leaving the page, so the consolidator copies
this block — pruned to the codes that actually appear — into each report:

```markdown
## Legend

- **Issue code** — `<lens>/<tier>-<number>`, e.g. `solid/major-5` = the 5th Major
  finding raised by the SOLID lens. The lens and severity are in the code itself.
- **Lenses**
  - `clean-arch` — clean-architecture: the component/dependency graph.
  - `ddd` — domain-driven design: is the domain modelled well? (analyze-only).
  - `solid` — the five SOLID class principles.
  - `gof` — Gang-of-Four design patterns.
  - `clean-code` — line-level craft (naming, function shape, comments).
  - `test-quality` — the test suite's own structure, craft, and stale-test tending.
- **Tiers** — all six lenses use `critical > major > minor` (clean-code and test-quality
  grade on the same three tiers, so their findings sit at their own tier, not down-filed).
  A code's tier word is its tier at first assignment — the section a finding sits
  under is the current truth if it was later re-tiered.
- **Principle / dimension abbreviations** (they appear on each finding's *Lens* line):
  SRP Single Responsibility · OCP Open/Closed · LSP Liskov Substitution ·
  ISP Interface Segregation · DIP Dependency Inversion (the five SOLID);
  ADP Acyclic Dependencies · SDP Stable Dependencies · SAP Stable Abstractions
  (clean-architecture component principles); test-quality names its dimension in words
  (structure · naming · one-behavior · no-logic · fixtures · assertions · parametrization ·
  over-mock · isolation · speed · stale).
- **Cross-reference labels** (used in *Grouped changes* and each finding's
  *Related* line — so "the same thing, seen twice" is never a puzzle):
  - **Primary** — owns the fix; applying it resolves the whole group.
  - **Same change** — a different lens/principle *view of the very same edit*.
  - **Fix mechanism** — names *how* the primary is fixed, not a separate edit
    (e.g. a DIP inversion is the mechanism that breaks an ADP cycle).
  - **Sub-symptom** — a smaller smell that disappears once the primary is applied.
  - **Rides along** — a distinct but adjacent fix best done in the same edit.
```

## Findings index (the report's dashboard — emit it right after Summary)

A multi-lens report is a wall of prose, and three things a reader most wants are
the hardest to extract from it: *which principle does each code break*, *what order
do I apply these in*, and *where does this run currently stand*. The index is one
scannable table that answers all three at a glance, so nobody reverse-engineers the
apply order from scattered *Related* lines or hunts a code's principle across pages.

- **One row per finding**, every actionable finding listed (grouped-change members
  included — the `Group role` column places them). Decode the Lens / Principle codes
  via the Legend.
- **Ordered by `Order`** — the recommended apply sequence, *not* merely tier order.
  It is Critical → Major → Minor **with dependency overrides made explicit**: a
  change that creates a module another moves into runs first; a grouped change is one
  job, so its members share one `Order` number (Primary row first). Ungrouped recs
  that must precede/follow another get ordered accordingly, not just by tier.
- **`Principle` is the "which principle broke" column** the plain code can't carry
  (the code encodes lens + tier + number, never SRP-vs-OCP). SOLID → `SRP`/`OCP`/…;
  clean-arch → `ADP`/`SDP`/`SAP`/`Dependency Rule`; ddd → the concept
  (`leaked language`, `missing port`); gof → the pattern; clean-code → its rule
  (`#4 DRY`, `#8 few args`). All decodable in the Legend.
- **`Status` mirrors each finding's `Status:` line** — so the index is a live progress
  board during apply, and the persisted overview at a glance after.

Follow the table with a short **Apply order** note: one line of *why* for any
non-obvious ordering (e.g. "group-2 before ddd/minor-2 — the split gives the
extracted function its home"). Obvious tier-order needs no note.

## Outcome (the persisted run summary — filled at Phase 5, not at generation)

The per-finding `Status:` lines and the Apply log are the raw ledger; the Outcome is
the *synthesis* a human — or the next session, after this one's context is gone —
reads first. Persisting it in the report is the whole point: the shared workflow's
Phase 5 summary otherwise lives only in chat and dies with the context window.
**Omit the section entirely on an audit-only run** (nothing was applied, so there is
no outcome — the index Status column, all `pending`, already says so).

## Shape

```markdown
# Code Quality — <project name> — <YYYY-MM-DD>

## Summary

- Scope: <path analyzed>, <N> source files, <languages>
- Test suite: <command> — <green / N failing at baseline / none found>
- Lenses run: clean-architecture, ddd (analyze), solid, gof, clean-code
  <note any that degraded or found nothing, e.g. "gof — no findings">
- Findings after dedup: <n> Critical, <n> Major, <n> Minor  (<k> findings folded into <g> grouped changes)
- Top wins: <the 3–5 recs a human should care about most across all lenses, one line each>

## Findings index

Recommended apply order top to bottom; grouped-change members share one Order (Primary first).
Decode Lens / Principle via the Legend.

| Order | Code | Tier | Lens · Principle | Group role | Title | Risk | Status |
|---|---|---|---|---|---|---|---|
| 1 | `solid/major-1` | Major | SOLID · SRP | group-2 · Primary | Split the 1889-line command god-module | Med | pending |
| 1 | `clean-code/major-1` | Major | clean-code · #4 DRY | group-2 · Rides along | Extract the 4-site credential read | Low | pending |
| 2 | `clean-arch/major-1` | Major | clean-arch · ADP | — | Break the 23-module import cycle | Low | pending |
| 3 | `clean-code/minor-1` | Minor | clean-code · #4 DRY | — | Extract the duplicated skeleton-report dict | Low | pending |

**Apply order.** <one line of *why* per non-obvious ordering; obvious tier order needs none — e.g.
"group-2 before ddd/minor-2 — the package split gives ddd/minor-2's extracted function its home.">

## Legend

<the Legend block above, pruned to the codes that appear in this report>

## Grouped changes

The most common source of confusion in a multi-lens report is several codes
describing **one** underlying edit. This is the map: each entry is one physical
change, listing every finding it resolves and *how* each relates, so a reader is
never left guessing why four codes point at the same lines. Findings that stand
alone are not listed here — they appear only under Recommendations. Omit this
whole section if nothing clustered.

### [group-1] One edit — <imperative title of the physical change>   [resolves <k> findings across <j> lenses]

Give every group a stable id (`group-1`, `group-2`, …) so the gate and apply can
reference it. The group's tier is its **Primary's** tier.

- **Primary** · `clean-arch/major-1` — <what it is, one line>. *Owns the fix.*
- **Same change** · `clean-arch/major-2` — <the same edge, a different violation>. *(subsumed — resolves with the Primary; not vetoable)*
- **Fix mechanism** · `solid/major-5` — <the how, not a separate edit>. *(subsumed)*
- **Sub-symptom** · `clean-arch/minor-2` — <vanishes once the primary lands>. *(subsumed)*
- **Rides along** · `clean-code/minor-5` — <adjacent cleanup enabled by the primary>. *(separable — its own step in the same job; vetoable)*

Apply `clean-arch/major-1` (subsumed riders resolve with it); then apply each
**Rides along** rider as a follow-on step in the *same* job, unless vetoed at the gate.
Omit any rider role that has no member. A group whose riders are all subsumed keeps
just the first clause.

## Recommendations

Full findings, grouped by tier (the gate reads these section headers). Every
finding keeps its owning lens's fields; the **Related** line is where the umbrella
adds the typed cross-reference so an overlap is legible in place. Precede each
finding with an explicit `<a id>` anchor — the ID with `/`→`-` — so *Full detail*
links (and any intra-report reference) resolve to the exact finding.

### Critical

<a id="solid-critical-1"></a>
#### [solid/critical-1] <short imperative title>

- **Lens:** SOLID — <SRP | OCP | LSP | ISP | DIP>   <!-- owning lens + its rubric hook; expand acronyms via the Legend -->
- **Location:** `path/to/file.py:120-310` <all affected sites>
- **Evidence:** <2–4 sentences, quoting the key lines — carried from the lens report>
- **Reader impact:** <why this hurts a human trying to understand or change the code>
- **Proposed change:** <concrete, behavior-preserving steps>
- **Risk:** <Low | Medium | High> — <what could break>
- **Related:** <one typed cross-ref per related finding, or "—">. When this finding
  belongs to a *Grouped change*, name the group and this finding's role so the link
  is unambiguous — e.g. `Fix mechanism in "Extract config_sync_fs.py leaf" (see
  Grouped changes); primary is clean-arch/major-1`. Use the Legend's labels
  (Primary / Same change / Fix mechanism / Sub-symptom / Rides along), never a bare
  ID list.
- **Full detail:** [../solid/SOLID-REPORT-<date>.md#solid-critical-1](../solid/SOLID-REPORT-<date>.md#solid-critical-1) <!-- relative to docs/reports/code-quality/; anchor = ID with `/`→`-` -->
- **Status:** pending

### Major

#### [clean-arch/major-1] ...

### Minor

#### [clean-code/minor-1] ...   <!-- every lens files at its own tier; clean-code is a peer, not down-filed -->

## Conflicts

Mutually-exclusive recs — applying one voids the other. The gate resolves each
before the apply order is computed; blanket/tier approval cannot resolve a fork.
Omit this whole section if there are no hard conflicts.

### [conflict-1] <one-line axis of disagreement>
- **Recs:** <id-A> vs <id-B>
- **Disagree about:** <the axis — e.g. "repository owns the query cache" vs "cache belongs in the service layer">
- **Consequence:** apply <id-A> ⟹ drop <id-B> (and vice versa)
- **Resolution:** <filled at the gate: winner id, or "neither">

## Cross-lens notes

For overlaps that did **not** collapse into a single shared edit (a hand-off to
another lens, or an overlap both lenses adjudicated to *no* action). One-edit
clusters belong in *Grouped changes* above, not here.

| Overlap | Filed as | Also flagged by | Resolution |
|---|---|---|---|
| type-switch on payment kind, adjudicated N/A | — (not filed) | gof (Strategy), solid (OCP) | both lenses ruled it a lateral move; no rec emitted |
| use-case imports the web framework | clean-arch/critical-1 (Dependency Rule) | ddd (missing port), solid (DIP) | one edit — see Grouped changes |

**Unresolved tensions** (surfaced, not auto-decided): <e.g. "Singleton (gof) vs
DIP (solid) on `Config` — the lenses disagree; decide at the gate", or "none">.

## Coverage & method

- Per lens: which ran, tool-assisted vs agent-driven (clean-architecture), any
  areas skipped, any lens that errored (recorded as a coverage gap, never silent).
- Baseline: <suite status before any change>

## Outcome

<!-- Written by the orchestrator at Phase 5, once an apply phase has run. Omit this
     whole section on an audit-only run. This is the persisted run summary — it must
     survive loss of the working session's context, so it lives here, not in chat. -->

- **Applied:** <group/rec ids that landed, one clause each — "group-2 (commands split + credential DRY); clean-arch/major-1 (cycle 23→14, residual left by design)">
- **Deferred / not approved:** <ids left pending, one-line why each, or "none">
- **Failed / reverted:** <ids that reverted + reason, or "none">
- **Suite:** <baseline → final, e.g. "1381 → 1388 passed, green"> · **Net diffstat:** <N files, +X/-Y> · **Checkpoints:** <N commits on the working branch>
- **Verification:** <how safety was proven, in aggregate — "all jobs on covered targets (existing suite exercised them, no pins needed)"; call out any legacy-mode job, e.g. "clean-arch/major-1 targets partly uncovered → 4 characterization pins written red-first">
- **Residual / next pass:** <pending recs, partial applies, and any newly-noticed smell recorded for a future cycle — never silently applied>

## Apply log

<!-- Appended by the implementer, one line per attempt, exactly as in the lens templates.
     The safety clause (existing-suite coverage source, or pins written red-first) is
     required — it is what makes "the engine actually ran a safe refactor" observable: -->
<!-- <UTC timestamp> [clean-arch/critical-1] applied — covered by test_boundaries.py — suite green (42 passed) — diffstat: 3 files, +120/-85 -->
<!-- <UTC timestamp> [gof/major-2] applied — uncovered targets → 3 pins written red-first (test_legacy_billing.py) — suite green (45 passed) — diffstat: 2 files, +80/-30 -->
```

The `Status:` vocabulary and the Apply-log line format are the shared ones defined
in [../../../docs/refactor-workflow.md](../../../docs/refactor-workflow.md)
("Status & Apply-log format") — identical to the lens templates, so the shared
implementer needs no special casing.
