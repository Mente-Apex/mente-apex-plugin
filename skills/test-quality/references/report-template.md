# test-quality report template

The reviewer writes
`docs/reports/test-quality/TEST-QUALITY-REPORT-<YYYY-MM-DD>.md` in exactly this shape.
Angle brackets are runtime fill-slots.

Rec IDs are self-describing: `test-quality/<tier>-<n>`, where `<tier>` ∈ `critical |
major | minor` — so `test-quality/major-1` reads as "the first Major finding from the
test-quality lens" with no legend lookup. The `test-quality/` prefix makes every ID
globally unique, so the code-quality umbrella carries it verbatim (no re-prefixing). IDs
are permanent once assigned; the tier word records the tier at first assignment, and if a
finding is later re-tiered the section heading it sits under is authoritative.

**Anchors.** Precede each finding heading with an explicit anchor — the ID with `/`→`-`,
e.g. `<a id="test-quality-critical-1"></a>` above `#### [test-quality/critical-1]` — so
the umbrella's *Full detail* links can jump straight to it.

Each finding carries a **Kind** line naming the rubric dimension it breaks
(`structure`, `naming`, `one-behavior`, `no-logic`, `fixtures`, `assertions`,
`parametrization`, `over-mock`, `isolation`, `speed`, `stale`) — this is the "which
principle" column the umbrella's Findings index reads.

Findings whose recommended action is **deletion** additionally carry a
**Coverage proof** line — deletions are never applied without it (see the SKILL's
deletion gate).

```markdown
# Test-quality Audit — <project> — <YYYY-MM-DD>

## Summary
- Scope: <test path>, <N> test files, <M> tests, <languages/runner>
- Test suite: <command> — <green / N failing at baseline>; coverage tool: <name / none>
- Findings: <n> Critical, <n> Major, <n> Minor
- Top wins: <the 2–3 that matter most, one line each — e.g. "3 dead tests referencing
  the deleted `LegacyExporter`; a flat 900-line test_core.py with no module architecture">

## Findings

### Critical
<a id="test-quality-critical-1"></a>
#### [test-quality/critical-1] <short imperative title, e.g. "Delete the 3 dead tests importing the removed LegacyExporter">
- **Kind:** <the rubric dimension, e.g. stale (dead)>
- **Location:** `tests/path:line` <all sites>
- **Evidence:** <what makes it a finding — the missing import, the mock-only assertion,
  the identical parametrized twin. No evidence, no finding.>
- **Impact:** <why it hurts trust/readability/change-safety — justifies the tier>
- **Fix:** <concrete: delete / merge into <test> / split into N tests / inject the port /
  extract a fixture>
- **Coverage proof:** <only for a deletion — the coverage evidence that removal loses no
  SUT coverage, or "N/A (not a deletion)">
- **Related:** <lens-overlap rec, e.g. "over-mock → solid DIP / ddd missing port", or none>
- **Risk:** <Low | Medium | High> — <what could break; a deletion or a de-mock is rarely Low>
- **Tier:** Critical
- **Status:** pending

### Major
#### [test-quality/major-1] ...

### Minor
#### [test-quality/minor-1] ...

## Reviewer notes
- Draft findings pruned as false positives: <finding → reason>, or "none"
- Related findings filed to other lenses (over-mocking design fixes, line craft): <ids>, or "none"
- Suspected-but-unproven duplicates kept (no coverage proof): <ids>, or "none"
- Areas not examined: <coverage gaps>

```

## Mutation gate

Written by `scripts/mutation_gate.py --report <this file>`, which replaces the
span between the two markers below and leaves every other byte of the report
alone — so re-running the gate updates this section in place rather than
stacking stale copies. The script does the writing, never the agent: the marker
contract is then covered by a test, and a guard that lives only in prose is the
unverifiable guard this lens exists to catch. Without `--report` the gate writes
no file at all, and this section keeps reading `_Not yet run._`.

Records the scope that produced this result, every survivor with the tests that
should have killed it, and anything inconclusive or unverifiable. Never a score
— a percentage is gameable and tells a reader nothing they can act on.

<!-- mutation-gate:begin -->
_Not yet run._
<!-- mutation-gate:end -->

This section sits in the real report between `## Reviewer notes` and
`## Apply log`, at the same top level as the rest of the template above and
below — it is broken out of the fenced block only so this reference doc's own
structure guard can address it as a real heading.

```markdown
## Apply log
<!-- Appended by the implementer, one line per attempt, per the canonical format in
     docs/refactor-workflow.md — with the safety clause (mutation gate result, or the
     coverage-non-regression proof for a deletion): -->
<!-- <UTC ts> [test-quality/major-2] applied — merged into test_export::…, mutation gate: broke SUT → test failed → restored — suite green (312 passed) — diffstat: 1 file, +6/-24 -->
<!-- <UTC ts> [test-quality/critical-1] applied (deletion) — coverage proof: removed 3 tests, SUT line/branch coverage unchanged (deleted symbol gone) — suite green (309 passed) — diffstat: 1 file, -41 -->
```

`Status:` vocabulary and the Apply-log line format are the shared ones in
[../../../docs/refactor-workflow.md](../../../docs/refactor-workflow.md)
("Status, Apply-log & Outcome format") — identical to the other lenses, so the shared
implementer needs no special casing beyond recording the gate result in the safety clause.
