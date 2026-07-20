# clean-code deep-review report template

The reviewer writes `docs/reports/clean-code/CLEAN-CODE-REPORT-<YYYY-MM-DD>.md` in
exactly this shape. IDs `G1,G2,…`, permanent once assigned. Angle brackets are
fill-slots.

```markdown
# Clean-code review — <scope> — <YYYY-MM-DD>

## Summary
- Scope: <paths / diff reviewed>, <N> files
- Findings: <n> High, <n> Medium, <n> Low
- Top items: <the 2–3 that matter most, one line each>

## Findings

### High
#### [G1] <short imperative title>
- **Principle:** <numbered standard principle>
- **Location:** `path/to/file.py:42` <all sites>
- **Evidence:** <quote the key lines>
- **Why it costs the reader:** <the concrete reader impact, not the rule name>
- **Suggestion:** <the concrete fix>
- **Severity:** High

### Medium
#### [M-style G<n>] ...

### Low
#### [G<n>] ...

## Hand-offs (not clean-code fixes)
- <structural issue> → `/solid` | `/gof` | `/ddd` | `/clean-architecture`, one line each

## Looks good
- <what is already clean and should be kept, incl. good why-comments>

## Reviewer notes
- Draft findings pruned as false positives: <finding → reason>, or "none"
- Areas not examined: <coverage gaps>
```
