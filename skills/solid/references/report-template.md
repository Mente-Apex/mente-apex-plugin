# Report template

The reviewer writes `solid-reports/SOLID-REFACTOR-<YYYY-MM-DD>.md` in exactly
this shape. The structure is load-bearing: the orchestrator parses tiers and
Risk fields to build the approval question, and the implementer updates Status
and the Apply log in place. Keep the field names verbatim.

Rec IDs: `C1, C2, …` (Critical), `M1, …` (Major), `N1, …` (Minor). IDs are
permanent once assigned — later cycles append, never renumber.

```markdown
# SOLID Refactor Plan — <project name> — <YYYY-MM-DD>

## Summary

- Scope: <path analyzed>, <N> source files, <languages>
- Test suite: <command> — <green / N failing at baseline / none found>
- Findings: <n> Critical, <n> Major, <n> Minor
- Top readability wins: <the 2–3 recs a human should care about most, one line each>

## Recommendations

### Critical

#### [C1] <short imperative title, e.g. "Split OrderManager god class">

- **Principle:** <SRP | OCP | LSP | ISP | DIP>
- **Location:** `path/to/file.py:120-310` <all affected sites>
- **Evidence:** <2–4 sentences describing what the code does now, quoting the
  key lines. No evidence, no finding.>
- **Reader impact:** <why this hurts a human trying to understand or change
  the code — the argument that justifies the tier>
- **Proposed change:** <concrete, behavior-preserving steps; name the new
  modules/classes/interfaces to be created>
- **Risk:** <Low | Medium | High> — <what could break; High explains why it
  needs individual human confirmation>
- **Verification:** <which existing tests cover this code; what to check after>
- **Status:** pending

### Major

#### [M1] ...

### Minor

#### [N1] ...

## Reviewer notes

- Draft findings pruned as false positives: <finding → one-line reason>, or "none"
- Findings added by the reviewer: <IDs>, or "none"
- Areas not examined: <anything skipped, so the human knows the coverage>

## Apply log

<!-- Appended by the implementer, one line per attempt: -->
<!-- <UTC timestamp> [C1] applied — suite green (42 passed) — diffstat: 3 files, +120/-85 -->
<!-- <UTC timestamp> [M2] FAILED — test_x broke, fix attempt failed, reverted -->
```

Status values: `pending` → `applied` | `failed (reverted)` | `skipped (not
approved)`. The implementer edits the Status line of each rec it touches and
appends to the Apply log; it changes nothing else in the report.
