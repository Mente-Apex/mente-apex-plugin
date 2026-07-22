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
re-prefixes. `<lens>` ∈ `clean-arch | ddd | solid | gof | clean-code`; `<tier>` ∈
`critical | major | minor` for **all five** lenses (clean-code grades line craft on
the same three tiers — see its standard's Severity rubric — so nothing needs
translating). So `solid/major-5`, `clean-arch/critical-1`, `clean-code/major-2` —
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
- **Tiers** — all five lenses use `critical > major > minor` (clean-code grades line
  craft on the same three tiers, so its findings sit at their own tier, not down-filed).
  A code's tier word is its tier at first assignment — the section a finding sits
  under is the current truth if it was later re-tiered.
- **Principle abbreviations** (they appear on each finding's *Lens* line):
  SRP Single Responsibility · OCP Open/Closed · LSP Liskov Substitution ·
  ISP Interface Segregation · DIP Dependency Inversion (the five SOLID);
  ADP Acyclic Dependencies · SDP Stable Dependencies · SAP Stable Abstractions
  (clean-architecture component principles).
- **Cross-reference labels** (used in *Grouped changes* and each finding's
  *Related* line — so "the same thing, seen twice" is never a puzzle):
  - **Primary** — owns the fix; applying it resolves the whole group.
  - **Same change** — a different lens/principle *view of the very same edit*.
  - **Fix mechanism** — names *how* the primary is fixed, not a separate edit
    (e.g. a DIP inversion is the mechanism that breaks an ADP cycle).
  - **Sub-symptom** — a smaller smell that disappears once the primary is applied.
  - **Rides along** — a distinct but adjacent fix best done in the same edit.
```

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

## Legend

<the Legend block above, pruned to the codes that appear in this report>

## Grouped changes

The most common source of confusion in a multi-lens report is several codes
describing **one** underlying edit. This is the map: each entry is one physical
change, listing every finding it resolves and *how* each relates, so a reader is
never left guessing why four codes point at the same lines. Findings that stand
alone are not listed here — they appear only under Recommendations. Omit this
whole section if nothing clustered.

### One edit — <imperative title of the physical change>   [resolves <k> findings across <j> lenses]

- **Primary** · `clean-arch/major-1` — <what it is, one line>. *Owns the fix.*
- **Same change** · `clean-arch/major-2` — <the same edge seen as a different violation>.
- **Fix mechanism** · `solid/major-5` — <the how, not a separate edit>.
- **Sub-symptom** · `clean-arch/minor-2` — <vanishes once the primary lands>.

Apply `clean-arch/major-1`; the rest resolve with it.

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

## Apply log

<!-- Appended by the implementer, one line per attempt, exactly as in the lens templates: -->
<!-- <UTC timestamp> [clean-arch/critical-1] applied — suite green (42 passed) — diffstat: 3 files, +120/-85 -->
```

The `Status:` vocabulary and the Apply-log line format are the shared ones defined
in [../../../docs/refactor-workflow.md](../../../docs/refactor-workflow.md)
("Status & Apply-log format") — identical to the lens templates, so the shared
implementer needs no special casing.
