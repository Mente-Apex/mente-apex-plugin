# Report template

The reviewer writes `docs/reports/solid/SOLID-REPORT-<YYYY-MM-DD>.md` in exactly
this shape. The structure is load-bearing: the orchestrator parses tiers and
Risk fields to build the approval question, and the implementer updates Status
and the Apply log in place. Keep the field names verbatim.

Rec IDs are self-describing: `solid/<tier>-<n>`, where `<tier>` ∈ `critical |
major | minor` — so `solid/major-1` reads as "the first Major finding from the
SOLID lens" with no legend lookup. The `solid/` prefix makes every ID globally
unique, so the code-quality umbrella carries it verbatim (no re-prefixing). IDs
are permanent once assigned — later cycles append, never renumber. The tier word
records the tier **at first assignment**; if a finding is later re-tiered, the
section heading it sits under is authoritative and the ID is left unchanged.

**Anchors.** Precede each finding heading with an explicit anchor — the ID with
`/`→`-`, e.g. `<a id="solid-critical-1"></a>` above `#### [solid/critical-1]` — so the
code-quality umbrella's *Full detail* links can jump straight to it (markdown's
auto-generated heading anchors don't handle the `/`).

```markdown
# SOLID Refactor Plan — <project name> — <YYYY-MM-DD>

## Summary

- Scope: <path analyzed>, <N> source files, <languages>
- Test suite: <command> — <green / N failing at baseline / none found>
- Findings: <n> Critical, <n> Major, <n> Minor
- Top readability wins: <the 2–3 recs a human should care about most, one line each>

## Recommendations

### Critical

<a id="solid-critical-1"></a>
#### [solid/critical-1] <short imperative title, e.g. "Split OrderManager god class">

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

#### [solid/major-1] ...

### Minor

#### [solid/minor-1] ...

## Reviewer notes

- Draft findings pruned as false positives: <finding → one-line reason>, or "none"
- Findings added by the reviewer: <IDs>, or "none"
- Areas not examined: <anything skipped, so the human knows the coverage>

## Apply log

<!-- Appended by the implementer, one line per attempt: -->
<!-- <UTC timestamp> [solid/critical-1] applied — suite green (42 passed) — diffstat: 3 files, +120/-85 -->
<!-- <UTC timestamp> [solid/major-2] FAILED — test_x broke, fix attempt failed, reverted -->
```

The `Status:` vocabulary and the Apply-log line format are defined once in the
shared workflow — see [../../../docs/refactor-workflow.md](../../../docs/refactor-workflow.md)
("Status & Apply-log format"). The skeleton above is what the reviewer lays down;
the implementer fills it per that spec.
