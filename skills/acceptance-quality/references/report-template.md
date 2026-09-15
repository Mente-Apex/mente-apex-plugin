# acceptance-quality report template

The reviewer writes
`docs/reports/acceptance-quality/ACCEPTANCE-QUALITY-REPORT-<YYYY-MM-DD>.md` in exactly this shape.
Angle brackets are runtime fill-slots. Field names, the ID scheme, and the anchor
rule are the canonical finding schema defined once in
[docs/report-contract.md](../../../docs/report-contract.md).

Rec IDs are self-describing: `acceptance-quality/<tier>-<n>`, where `<tier>` ∈ `critical |
major | minor` — so `acceptance-quality/major-1` reads as "the first Major finding from the
acceptance-quality lens" with no legend lookup. The `acceptance-quality/` prefix makes every ID
globally unique, so the code-quality umbrella carries it verbatim (no re-prefixing). IDs
are permanent once assigned; the tier word records the tier at first assignment, and if a
finding is later re-tiered the section heading it sits under is authoritative.

**Anchors.** Precede each finding heading with an explicit anchor — the ID with `/`→`-`,
e.g. `<a id="acceptance-quality-critical-1"></a>` above `#### [acceptance-quality/critical-1]` — so
the umbrella's *Full detail* links can jump straight to it.

Each finding carries a **Kind** line naming the rubric dimension it breaks
(`spec-as-spec`, `leakage`, `coverage`, `coupling`, `definitions`, `consistency`,
`stale`) — this is the "which principle" column the umbrella's Findings index reads.

A finding that changes what a scenario **means** carries a **Conversation** line
instead of a mechanical proposal: a scenario is agreed behaviour, so rewriting one
is a discussion with the people who agreed it, never a batch apply. Mechanical
findings — an extracted duplicate step, a consistent rename — carry an ordinary
Proposed change.

```markdown
# Acceptance-quality Audit — <project> — <YYYY-MM-DD>

## Summary
- Scope: <acceptance path>, <N> feature files, <M> scenarios, <dialect/runner>
- Acceptance suite: <command> — <green / N failing at baseline / not run>
- Dialect: <gherkin / other> — the `references/<dialect>.md` that was loaded
- Findings: <n> Critical, <n> Major, <n> Minor
- Top wins: <the 2–3 that matter most, one line each — e.g. "3 dead tests referencing
  the deleted `LegacyExporter`; a flat 900-line test_core.py with no module architecture">

## Findings

### Critical
<a id="acceptance-quality-critical-1"></a>
#### [acceptance-quality/critical-1] <short imperative title, e.g. "Delete the 3 dead tests importing the removed LegacyExporter">
- **Kind:** <the rubric dimension: spec-as-spec | leakage | coverage | coupling | definitions | consistency | stale>
- **Location:** `features/path:line` <all sites; for a consistency finding, the
  count and a representative few rather than all 31>
- **Evidence:** <quote the scenario text — this lens's findings are about what a reader
  sees, so the quote IS the evidence. No evidence, no finding.>
- **Reader impact:** <why it hurts trust/readability/change-safety — justifies the tier>
- **Proposed change:** <concrete: name one concept one way / split into N scenarios /
  move the precondition into a Given / merge the duplicate step definitions>
- **Conversation:** <only where the change alters what a scenario MEANS — who needs to
  agree, and what the question is. "N/A (mechanical)" otherwise.>
- **Related:** <lens-overlap rec, e.g. "leaked domain term → ddd ubiquitous language", or none>
- **Risk:** <Low | Medium | High> — <what could break; anything touching a scenario's
  meaning is never Low>
- **Tier:** Critical
- **Status:** pending

### Major
<a id="acceptance-quality-major-1"></a>
#### [acceptance-quality/major-1] ...

### Minor
<a id="acceptance-quality-minor-1"></a>
#### [acceptance-quality/minor-1] ...

## Coverage & method

Per the plugin's status vocabulary — `ran` / `degraded` / `unverified`, one
line each, and **every `unverified` states its reason**. Absence is data,
never silence.

| What | Status | Note |
|---|---|---|
| <check or measurement> | <ran \| degraded \| unverified> | <rung that ran, what was skipped, or why it did not run> |

## Reviewer notes
- Draft findings pruned as false positives: <finding → reason>, or "none"
- Related findings filed to other lenses (over-mocking design fixes, line craft): <ids>, or "none"
- Suspected-but-unproven duplicates kept (no coverage proof): <ids>, or "none"
- Areas not examined: <coverage gaps>

## Outcome

<!-- Written by the orchestrator at Phase 5, once an apply phase has run — the
     persisted run synthesis (applied/deferred/failed ids, suite before/after,
     net diffstat, verification method, residuals). Omit this whole section
     entirely on an audit-only run; format per refactor-workflow.md. -->

## Apply log
<!-- Appended by the implementer, one line per attempt, per the canonical format in
     docs/refactor-workflow.md — with the safety clause (acceptance suite run result, or the
     coverage-non-regression proof for a deletion): -->
<!-- <UTC ts> [acceptance-quality/major-2] applied — one term per concept ('the customer', 31 scenarios) — acceptance suite green (48 scenarios) — diffstat: 6 files, +31/-31 -->
<!-- <UTC ts> [acceptance-quality/critical-1] applied (stale scenario deleted) — the step it pinned names a screen removed in #402 — acceptance suite green (47 scenarios) — diffstat: 1 file, -18 -->
```

`Status:` vocabulary and the Apply-log line format are the shared ones in
[../../../docs/refactor-workflow.md](../../../docs/refactor-workflow.md)
("Status, Apply-log & Outcome format") — identical to the other lenses. Per that file's
Phase 4 dispatch rule (lens ships one → use it, otherwise the shared
`docs/refactor-agents/implementer.md`), an acceptance-quality rec runs through the
**shared** implementer: this lens ships none of its own, because it has no extra safety
gate to add — its restraint is a tiering rule (a change to what a scenario MEANS is a
conversation, carried on the finding's `Conversation` line) rather than a mechanical
gate. The safety clause on the Apply-log line is the acceptance suite's own result.
