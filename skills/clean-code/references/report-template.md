# clean-code deep-review report template

The reviewer writes `docs/reports/clean-code/CLEAN-CODE-REPORT-<YYYY-MM-DD>.md` in
exactly this shape. Angle brackets are fill-slots.

Rec IDs are self-describing: `clean-code/<severity>-<n>`, where `<severity>` ∈
`critical | major | minor` — the **same tier vocabulary the other four lenses use**,
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
- **Severity:** Critical

### Major
#### [clean-code/major-1] ...

### Minor
#### [clean-code/minor-1] ...

## Hand-offs (not clean-code fixes)
- <structural issue> → `/solid` | `/gof` | `/ddd` | `/clean-architecture`, one line each

## Looks good
- <what is already clean and should be kept, incl. good why-comments>

## Reviewer notes
- Draft findings pruned as false positives: <finding → reason>, or "none"
- Areas not examined: <coverage gaps>
```
