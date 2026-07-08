# GoF report template

The reviewer writes `gof-reports/GOF-ANALYSIS-<YYYY-MM-DD>.md` in exactly this
shape. IDs (`C*/M*/N*`), `Risk`, and `Status` are load-bearing (parsed by the
apply phase). IDs are permanent once assigned — later cycles append, never
renumber.

Rec IDs: `C1, C2, …` (Critical), `M1, …` (Major), `N1, …` (Minor).

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
- **Overlap:** <SOLID principle / "none">

## Recommendations

### Critical

#### [C1] <imperative title, e.g. "Introduce Strategy for the pricing dispatch">

- **Pattern:** <one of the 23>
- **Location:** `file:line` <all sites>
- **Problem now:** <the concrete pain: duplicated/forced/missing structure>
- **Proposed change:** <behavior-preserving steps; name new classes/protocols>
- **Expected benefit:** <what becomes easier/safer>
- **Overlap:** <SOLID principle + any existing solid-reports rec ID, or "none">
- **Risk:** <Low|Medium|High> — <what could break>
- **Verification:** <which tests cover this; what to check after>
- **Status:** pending

### Major

#### [M1] ...

### Minor

#### [N1] ...

## Not applicable

| Pattern | Reason |
|---|---|
| <pattern> | <one line> |

## Reviewer notes

- Draft findings pruned as false positives: <finding → one-line reason>, or "none"
- Findings added by the reviewer: <IDs>, or "none"
- Areas not examined: <anything skipped, so the human knows the coverage>
- Cross-lens references: <solid-reports rec IDs this analysis references, or "none">

## Apply log

<!-- Appended by the implementer, one line per attempt: -->
<!-- <UTC timestamp> [C1] applied — suite green (42 passed) — diffstat: 2 files, +80/-30 -->
<!-- <UTC timestamp> [M2] FAILED — test_x broke, fix attempt failed, reverted -->
```

Status values: `pending` → `applied` | `failed (reverted)` | `skipped (not
approved)`. The implementer edits the Status line of each rec it touches and
appends to the Apply log; it changes nothing else in the report.

A rec's `Overlap:` field renders a ⚠ tension inline, e.g.: `**Overlap:** ⚠
SOLID DIP tension — a module-level singleton is itself a DIP smell; surface
the trade-off to the human rather than auto-recommending`.
