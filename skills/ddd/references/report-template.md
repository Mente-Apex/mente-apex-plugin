# DDD analyze report template

The reviewer writes `docs/reports/ddd/DDD-REFACTOR-<YYYY-MM-DD>.md` in exactly this
shape. Structure is load-bearing — the orchestrator reads tiers to build the
summary. Field names verbatim. IDs: `C1,C2,…` (Critical), `M1,…` (Major),
`N1,…` (Minor); permanent once assigned.

This mode is **report-only** — there is no Status transition to `applied` and no
apply log; `Status: pending` simply records that the finding is unactioned.

```markdown
# DDD Refactor Plan — <project name> — <YYYY-MM-DD>

## Summary

- Scope: <path analyzed>, <N> source files, <languages>
- Test suite: <command> — <green / N failing / none found> (context only; this
  mode runs no tests and changes no code)
- Findings: <n> Critical, <n> Major, <n> Minor
- Top wins: <the 2–3 findings a human should care about most, one line each>

## Findings

### Critical

#### [C1] <short imperative title, e.g. "Lift order pricing out of the HTTP controller">

- **Smell:** <anemic domain model | domain logic in controller/ORM model |
  missing port (direct DB/HTTP in domain) | fat repository | aggregate without
  invariant | transaction script | leaked ubiquitous language>
- **Location:** `path/to/file.py:120-180` <all affected sites>
- **Evidence:** <2–4 sentences quoting the key lines. No evidence, no finding.>
- **Impact:** <why this hurts comprehension/change safety — justifies the tier>
- **Toward DDD:** <concrete target: which entity/VO/aggregate/port this becomes,
  where the logic should live, what boundary to introduce>
- **Tier:** Critical
- **Status:** pending

### Major

#### [M1] ...

### Minor

#### [N1] ...

## Target architecture sketch

<the hexagon this code is trying to be: the bounded context(s), the aggregates
and their invariants, the ports the domain needs, and which existing modules map
to domain / application / adapters / web>

## Reviewer notes

- Draft findings pruned as false positives: <finding → one-line reason>, or "none"
- Findings added by the reviewer: <IDs>, or "none"
- Areas not examined: <coverage gaps>
- Reverse-engineered docs/domain proposal: <written / kept / discarded by user>
```
