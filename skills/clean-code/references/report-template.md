# clean-code deep-review report template

The reviewer writes `docs/reports/clean-code/CLEAN-CODE-REPORT-<YYYY-MM-DD>.md` in
exactly this shape. Angle brackets are fill-slots. Field names, the ID scheme,
and the anchor rule are the canonical finding schema defined once in
[docs/report-contract.md](../../../docs/report-contract.md); `Risk` and `Status`
are load-bearing (parsed by the apply phase) — this lens's own run stops at
Phases 0–3, but a finding merged by the umbrella (or opted into) is applicable
through the shared engine. `Why it costs the reader` and `Suggestion` are this
lens's declared aliases for the canonical `Reader impact` and `Proposed change`
fields (see that doc's alias table).

Rec IDs are self-describing: `clean-code/<tier>-<n>`, where `<tier>` ∈
`critical | major | minor` — the **same tier vocabulary the other five lenses use**,
so `clean-code/major-2` reads as "the second Major clean-code finding" with no
legend lookup and no cross-scale translation. Grade each finding against the
standard's Severity rubric (`../../../docs/clean-code-standard.md`), which uses
these same three levels. The `clean-code/` prefix makes every ID globally unique,
so the code-quality umbrella carries it verbatim and files each finding at its own
tier — clean-code is a peer lens, not down-filed. IDs are permanent once assigned.

**Anchors.** Precede each finding heading with an explicit anchor — the ID with
`/`→`-`, e.g. `<a id="clean-code-critical-1"></a>` above `#### [clean-code/critical-1]` —
so the code-quality umbrella's *Full detail* links can jump straight to it (markdown's
auto-generated heading anchors don't handle the `/`).

```markdown
# Clean-code review — <scope> — <YYYY-MM-DD>

## Summary
- Scope: <paths / diff reviewed>, <N> files
- Findings: <n> Critical, <n> Major, <n> Minor
- Top items: <the 2–3 that matter most, one line each>

## Findings

### Critical
<a id="clean-code-critical-1"></a>
#### [clean-code/critical-1] <short imperative title>
- **Principle:** <numbered standard principle>
- **Location:** `path/to/file.py:42` <all sites>
- **Evidence:** <quote the key lines>
- **Why it costs the reader:** <the concrete reader impact, not the rule name>
- **Suggestion:** <the concrete fix>
- **Risk:** <Low | Medium | High> — <what could break if this is applied>
- **Severity:** Critical
- **Status:** pending

### Major
<a id="clean-code-major-1"></a>
#### [clean-code/major-1] ...

### Minor
<a id="clean-code-minor-1"></a>
#### [clean-code/minor-1] ...

## Hand-offs (not clean-code fixes)
- <structural issue> → `/solid` | `/gof` | `/ddd` | `/clean-architecture`, one line each

## Looks good
- <what is already clean and should be kept, incl. good why-comments>

## Coverage & method

Per the plugin's status vocabulary — `ran` / `degraded` / `unverified`, one
line each, and **every `unverified` states its reason**. Absence is data,
never silence.

| What | Status | Note |
|---|---|---|
| <check or measurement> | <ran \| degraded \| unverified> | <rung that ran, what was skipped, or why it did not run> |

## Reviewer notes
- Draft findings pruned as false positives: <finding → reason>, or "none"
- Areas not examined: <coverage gaps>

## Outcome

<!-- Written by the orchestrator at Phase 5, once an apply phase has run — the
     persisted run synthesis (applied/deferred/failed ids, suite before/after,
     net diffstat, verification method, residuals). Omit this whole section
     entirely on an audit-only run; format per refactor-workflow.md. -->

## Apply log

<!-- Appended by the implementer, one line per attempt: -->
<!-- <UTC timestamp> [clean-code/critical-1] applied — suite green (42 passed) — diffstat: 1 file, +12/-8 -->
<!-- <UTC timestamp> [clean-code/major-2] FAILED — test_x broke, fix attempt failed, reverted -->
```

The `Status:` vocabulary and the Apply-log line format are defined once in the
shared workflow — see [../../../docs/refactor-workflow.md](../../../docs/refactor-workflow.md)
("Status & Apply-log format"). The skeleton above is what the reviewer lays down;
the implementer fills it per that spec.
