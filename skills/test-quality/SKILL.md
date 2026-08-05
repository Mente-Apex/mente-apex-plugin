---
name: test-quality
description: >-
  Audit an existing TEST SUITE as a subject in its own right — the health question none
  of the production-code lenses (solid, gof, ddd, clean-architecture, clean-code) is built
  to answer. Checks suite structure and organization (do test modules mirror the code? are
  tests grouped into cohesive classes/describe blocks, or a flat pile of functions with no
  architecture?), test craft (name-as-spec, Arrange-Act-Assert, one behavior per test, no
  logic in tests, fixture/factory design, assertion quality, parametrization), test
  strategy (over-mocking / mocking your own domain as a DIP smell, isolation, speed/markers),
  and — critically — TENDING: detecting stale/redundant tests (dead tests referencing
  removed code, provable duplicates, obsolete pins, vacuous mock-only tests) so a suite that
  only ever grows finally gets cleaned. Analyze-first / report-only by default because test
  changes are risky; opt-in apply reuses the TDD refactor engine with two extra safety gates
  (a mutation gate for refactors, a coverage-non-regression gate for deletions). Reuses the
  tdd skill as its standard. Use for "/test-quality", test suite review, test smells, test
  organization, flaky/coupled tests, too much mocking, dead or redundant tests, "our test
  suite is a mess / only grows / never gets cleaned", "are these good tests?".
user-invocable: true
metadata:
  version: "0.2.0"
  source: "Kent Beck TDD + the plugin's tdd skill, read pragmatically"
---

# test-quality — is this a healthy test suite?

The lenses `solid`/`gof`/`ddd`/`clean-architecture`/`clean-code` all read the *production*
code and use the test suite only as a safety-net tripwire. **None of them audits the tests
themselves.** This lens does: it treats the suite as a subject — its structure, craft,
strategy, and accumulated cruft — and asks whether a human can trust, read, and extend it.
It runs on the shared engine
([../../docs/refactor-workflow.md](../../docs/refactor-workflow.md)) with its own rubric,
audit-first like `clean-architecture`.

**Its standard is the `tdd` skill, reused not restated.** The definition of a good test
already lives in [../tdd/SKILL.md](../tdd/SKILL.md) and its references
(`ddd_testing.md`, the per-stack adapters). This lens is the *audit* against that standard —
it links those files rather than re-deriving what a good test is.

## The carve (why it doesn't fight the others)

- **vs `clean-code`:** clean-code owns *line craft*, including inside a test file; this
  owns everything *test-specific* — suite structure, test-as-spec, mocking strategy,
  isolation, and stale-test tending. See [references/rubric.md](references/rubric.md).
- **vs `solid`/`ddd`:** **over-mocking** is a production design smell (missing port / DIP).
  File the fix there via [../../docs/lens-overlap.md](../../docs/lens-overlap.md); this
  names the test-side symptom and cross-references.

## Invocation

`/test-quality [scope]`

- `scope` is a path, a diff, or a range, scoping the audit to a test tree/subtree (default: the repo's tests).
- Report-only is the default outcome; applying anything is opt-in at the gate.
- Pre-authorizations count as the human review for what they cover.

## Flow (audit-first; apply opt-in and conservative)

Follows the shared workflow, Phases 0–3; apply (4–5) is opt-in and guarded.

1. **Phase 0 — Inventory & baseline.** Scope the **test** tree, detect the runner and its
   coverage tool, run the suite once for the baseline, create git-excluded
   `docs/reports/test-quality/`.
2. **Phase 1 — Analyzer** ([agents/analyzer.md](agents/analyzer.md); read-only over the
   suite, writes its own draft) reads
   `references/rubric.md` and the `tdd` references, drafts findings → `draft-findings.md`.
   The analyzer also runs the **mutation sweep** — the only thing that catches
   *born-vacuous* tests, which no post-refactor gate would ever reach. By default it
   covers the **diff** (`--scope merge-base`), so on a stand-alone audit of an untouched
   tree it selects zero files and proves nothing. That case is reachable, not free: the
   analyzer offers an explicit narrowed sweep (`--scope full --paths <subtree>`) over the
   highest-value part of the test tree, quotes the cost, and records what was left
   uncovered as a Coverage note. Whole-repo mutation stays too slow to be a default.
3. **Phase 2 — Reviewer** ([agents/reviewer.md](agents/reviewer.md)) re-verifies every
   finding against the real tests, tiers Critical/Major/Minor, cross-references the hub,
   and writes `docs/reports/test-quality/TEST-QUALITY-REPORT-<YYYY-MM-DD>.md` per
   [references/report-template.md](references/report-template.md).
4. **Phase 3 — Decision gate.** Present the summary. Most findings stay advisory; applying
   is opt-in and per the two gates below.

## Applying is guarded by two gates (the reason this lens is report-first)

Changing tests is riskier than changing production code, and the usual "suite still green"
proof is *worthless* here — a weakened **or deleted** test also leaves the suite green. So
the opt-in [agents/implementer.md](agents/implementer.md) never trusts green alone:

- **Refactor a test** (rename, split, merge, restructure, de-mock) → the TDD refactor
  engine **plus the mutation gate** (`scripts/mutation_gate.py`): mutate the code under
  test mechanically and confirm the refactored test *fails*. Proves the test still catches
  its bug, not just that it still passes. The manual break-and-restore loop stays as the
  fallback where no mutation tool is available.
- **Delete a stale test** → the **inverse, coverage-non-regression gate**: never
  auto-delete; remove the candidate, run coverage on the SUT, and keep it unless its
  *uniquely-covered* lines/branches are still covered elsewhere. If coverage drops, the
  test was the sole guard of that path — keep it. **Prefer merge over delete** (fold a
  narrow test into a parametrized case) so intent is preserved. Dead tests that fail to
  import are the one clear-cut delete — still surfaced for sign-off.
  **No coverage tool (Phase 0 recorded `coverage tool: none`) ⇒ no deletion recs at
  all** — made explicit rather than left implicit: the gate's proof is a coverage
  measurement, so without a coverage tool the reviewer cannot produce one and must not
  nominate a deletion; record the gap as a Coverage note instead (a dead test that
  fails to import is still the one exception, since its "proof" is the missing symbol,
  not a coverage run).

## Guardrails

- **Report-first, always.** Default outcome is the report; no test is touched without an
  explicit opt-in, and every deletion is a per-test human decision.
- **Green is not proof.** Neither a refactored nor a deleted test is "safe" because the
  suite stays green — the gates above are what prove safety.
- **Defer, don't duplicate.** Over-mocking's *fix* is a `solid`/`ddd` finding; line craft
  in a test is `clean-code`'s. File each shared smell once via the hub.
- **Judgment, not dogma.** Honour the when-NOT-to rules in the rubric: don't demand
  class scaffolding a tiny cohesive file hasn't earned; a "duplicate" you can't prove
  redundant by coverage is not redundant.
- **The report is the single source of truth**; Status and apply logs live in it.

## File map

- [references/rubric.md](references/rubric.md) — the tiered rubric, the carve, when-NOT-to.
  Both analysis agents read it first.
- [references/report-template.md](references/report-template.md) — report format.
- [agents/analyzer.md](agents/analyzer.md), [agents/reviewer.md](agents/reviewer.md),
  [agents/implementer.md](agents/implementer.md) — the three roles.
- [../tdd/SKILL.md](../tdd/SKILL.md) + its references — the reused test standard.
- [../../docs/refactor-workflow.md](../../docs/refactor-workflow.md) — shared Phase 0–5.
- [../../docs/lens-overlap.md](../../docs/lens-overlap.md) — cross-lens reconciliation.
