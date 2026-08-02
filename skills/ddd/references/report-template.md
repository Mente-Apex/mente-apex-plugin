# DDD analyze report template

The reviewer writes `docs/reports/ddd/DDD-REPORT-<YYYY-MM-DD>.md` in exactly this
shape. Structure is load-bearing — the orchestrator reads tiers to build the
summary. Field names verbatim.

Rec IDs are self-describing: `ddd/<tier>-<n>`, where `<tier>` ∈ `critical | major
| minor` — so `ddd/major-1` reads as "the first Major finding from the DDD lens"
with no legend lookup. The `ddd/` prefix makes every ID globally unique, so the
code-quality umbrella carries it verbatim (no re-prefixing). IDs are permanent
once assigned. The tier word records the tier **at first assignment**; if a
finding is later re-tiered, the section heading it sits under is authoritative and
the ID is left unchanged.

This mode is **report-only** — there is no Status transition to `applied` and no
apply log; `Status: pending` simply records that the finding is unactioned.

**Anchors.** Precede each finding heading with an explicit anchor — the ID with
`/`→`-`, e.g. `<a id="ddd-critical-1"></a>` above `#### [ddd/critical-1]` — so the
code-quality umbrella's *Full detail* links can jump straight to it (markdown's
auto-generated heading anchors don't handle the `/`).

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

<a id="ddd-critical-1"></a>
#### [ddd/critical-1] <short imperative title, e.g. "Lift order pricing out of the HTTP controller">

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

#### [ddd/major-1] ...

### Minor

#### [ddd/minor-1] ...

## Target architecture sketch

<the hexagon this code is trying to be: the bounded context(s), the aggregates
and their invariants, the ports the domain needs, and which existing modules map
to domain / application / adapters / web>

## Coverage & method

Per [docs/status-vocabulary.md](../../../docs/status-vocabulary.md) — `ran` / `degraded` /
`unverified`, one line each, and **every `unverified` states its reason**. Absence
is data, never silence.

| What | Status | Note |
|---|---|---|
| <check or measurement> | <ran \| degraded \| unverified> | <rung that ran, what was skipped, or why it did not run> |

## Reviewer notes

- Draft findings pruned as false positives: <finding → one-line reason>, or "none"
- Findings added by the reviewer: <IDs>, or "none"
- Areas not examined: <coverage gaps>
- Reverse-engineered docs/domain proposal: <written / kept / discarded by user>
```
