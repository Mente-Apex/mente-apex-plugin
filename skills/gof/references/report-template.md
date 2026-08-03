# GoF report template

The reviewer writes `docs/reports/gof/GOF-REPORT-<YYYY-MM-DD>.md` in exactly this
shape. Rec IDs, `Risk`, and `Status` are load-bearing (parsed by the apply phase).
Field names, the ID scheme, and the anchor rule are the canonical finding schema
defined once in [docs/report-contract.md](../../../docs/report-contract.md) —
`Problem now` and `Expected benefit` are this lens's declared alias pair for the
canonical `Reader impact` field (see that doc's alias table).

Rec IDs are self-describing: `gof/<tier>-<n>`, where `<tier>` ∈ `critical | major
| minor` — so `gof/major-1` reads as "the first Major finding from the GoF lens"
with no legend lookup. The `gof/` prefix makes every ID globally unique, so the
code-quality umbrella carries it verbatim (no re-prefixing). IDs are permanent
once assigned — later cycles append, never renumber. The tier word records the
tier **at first assignment**; if a finding is later re-tiered, the section heading
it sits under is authoritative and the ID is left unchanged.

**Anchors.** Precede each finding heading with an explicit anchor — the ID with
`/`→`-`, e.g. `<a id="gof-critical-1"></a>` above `#### [gof/critical-1]` — so the
code-quality umbrella's *Full detail* links can jump straight to it (markdown's
auto-generated heading anchors don't handle the `/`).

```markdown
# GoF Analysis — <project> — <YYYY-MM-DD>

## Summary

- Scope: <path>, <N> source files
- Test suite: <command> — <green / N failing / none>
- Detected patterns: <name [grade], ...> · Maturity: <Nascent/Emerging/Moderate/Mature>
- Recommendations: <n> Critical, <n> Major, <n> Minor
- Top wins: <2–3 recs a human should care about, one line each>

## Detected patterns (graded inventory — informational)

### [Category] · <Pattern> — Grade: <letter — full label>

- **Location**: `path/to/file.py` → `ClassName`
- **Evidence**: <the structural elements/method names that identify the pattern>
- **Strengths**: <what the implementation gets right, with specific references>
- **Issues**: <concrete problems and why they matter>
- **Recommendation**: <one actionable improvement>
- **Related:** <SOLID principle / "none">

## Findings

### Critical

<a id="gof-critical-1"></a>
#### [gof/critical-1] <imperative title, e.g. "Introduce Strategy for the pricing dispatch">

- **Pattern:** <one of the 23>
- **Location:** `file:line` <all sites>
- **Evidence:** <the structural elements/method names that show the smell — quote
  the key lines. No evidence, no finding.>
- **Problem now:** <the concrete pain: duplicated/forced/missing structure>
- **Proposed change:** <behavior-preserving steps; name new classes/protocols>
- **Expected benefit:** <what becomes easier/safer>
- **Related:** <SOLID principle + any existing solid rec ID, or "none">
- **Risk:** <Low|Medium|High> — <what could break>
- **Verification:** <which tests cover this; what to check after>
- **Status:** pending

### Major

<a id="gof-major-1"></a>
#### [gof/major-1] ...

### Minor

<a id="gof-minor-1"></a>
#### [gof/minor-1] ...

## Not applicable

| Pattern | Reason |
|---|---|
| <pattern> | <one line> |

## Coverage & method

Per the plugin's status vocabulary — `ran` / `degraded` / `unverified`, one
line each, and **every `unverified` states its reason**. Absence is data,
never silence.

| What | Status | Note |
|---|---|---|
| <check or measurement> | <ran \| degraded \| unverified> | <rung that ran, what was skipped, or why it did not run> |

## Reviewer notes

- Draft findings pruned as false positives: <finding → one-line reason>, or "none"
- Findings added by the reviewer: <IDs>, or "none"
- Areas not examined: <anything skipped, so the human knows the coverage>
- Cross-lens references: <solid rec IDs this analysis references, or "none">

## Outcome

<!-- Written by the orchestrator at Phase 5, once an apply phase has run — the
     persisted run synthesis (applied/deferred/failed ids, suite before/after,
     net diffstat, verification method, residuals). Omit this whole section
     entirely on an audit-only run; format per refactor-workflow.md. -->

## Apply log

<!-- Appended by the implementer, one line per attempt: -->
<!-- <UTC timestamp> [gof/critical-1] applied — suite green (42 passed) — diffstat: 2 files, +80/-30 -->
<!-- <UTC timestamp> [gof/major-2] FAILED — test_x broke, fix attempt failed, reverted -->
```

The `Status:` vocabulary and the Apply-log line format are defined once in the
shared workflow — see [../../../docs/refactor-workflow.md](../../../docs/refactor-workflow.md)
("Status & Apply-log format"). The skeleton above is what the reviewer lays down;
the implementer fills it per that spec.

A rec's `Related:` field renders a ⚠ tension inline, e.g.: `**Related:** ⚠
SOLID DIP tension — a module-level singleton is itself a DIP smell; surface
the trade-off to the human rather than auto-recommending`.
