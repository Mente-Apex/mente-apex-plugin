# test-quality rubric — is this a healthy test suite?

Calibration, not a lesson. This lens audits the **test suite as a subject** — its
structure, its craft, and its accumulated cruft — a question none of the five
production-code lenses (`solid`/`gof`/`ddd`/`clean-architecture`/`clean-code`) is built
to answer. Every finding must argue its impact on a human trying to trust, read, or
change the tests.

**The substrate is the `tdd` skill — link, don't restate.** The authoring standard for
good tests already lives in [../../tdd/SKILL.md](../../tdd/SKILL.md) (the REFACTOR
checklist, one-behavior-per-test, name-as-spec, Arrange-Act-Assert),
[../../tdd/references/ddd_testing.md](../../tdd/references/ddd_testing.md) (mocking your
own domain is a design smell), and the per-stack adapters
(`../../tdd/references/<language>-<runner>.md`). This lens is the *audit* of a suite
against that standard; it reuses those references rather than re-deriving them.

## The carve (why it doesn't fight the others)

- **vs `clean-code`:** clean-code owns *line craft*, including inside test files
  (a badly-named variable in a test is clean-code's). This lens owns everything
  *test-specific*: suite **structure/organization**, test-as-spec, mocking strategy,
  isolation, assertion quality, and **stale-test tending**. When a smell is pure line
  craft, defer to clean-code; when it is about the suite *as a test suite*, file it here.
- **vs `solid`/`ddd`:** **over-mocking** (a test must mock your own domain to run) is a
  *production* design smell — a missing seam / DIP violation. File the design fix under
  `solid`/`ddd` per the hub; this lens names the test-side symptom and cross-references.
- **vs the production lenses generally:** they read `src/`; this reads `tests/`.

## Tiers (Critical / Major / Minor — when in doubt, down)

- **Critical** — the suite is actively misleading: a test that asserts nothing, only
  asserts a mock (tautological), or is **dead** (references removed code / can't import).
  Green here buys false confidence — the worst state a suite can be in.
- **Major** — structural or strategic rot that makes the suite hard to trust or extend:
  no module/class architecture, pervasive over-mocking, shared-state coupling between
  tests, one giant test asserting ten behaviors.
- **Minor** — local craft and hygiene: a weakly-named test, a message-string assertion
  where a type belongs, duplication a fixture would remove, a missing `slow` marker.

## Dimensions

Each dimension's **Kind** slug (in parens) is the exact value the report template's
`Kind:` field takes — the same 11 slugs `references/report-template.md` and the
`code-quality` umbrella's template already enumerate; naming them here too means the
analyzer, which reads this rubric and never those templates, files findings under the
canonical slug the first time instead of a label the reviewer has to reconcile.

### Structure & organization (the "no module/class architecture" concern)
1. **Suite structure.** (`structure`) Test modules mirror the SUT (a `tests/` layout or
   co-located `*.test.ts` that maps to source); related tests grouped into cohesive
   classes / `describe` blocks, not a flat pile of top-level `test_*` functions with no
   architecture. *Smell:* a 900-line `test_everything.py` spanning six unrelated
   concerns; tests for one module scattered across many files with no discoverable home.
2. **Naming as spec.** (`naming`) Test names read as behavior specifications
   (`test_rejects_duplicate_email`), not `test_1` / `test_it_works` / `test_foo`.

### Craft
3. **One behavior per test; Arrange-Act-Assert.** (`one-behavior`) A test that exercises
   several behaviors hides *which* spec broke. AAA structure is visible, not tangled.
4. **No logic in tests.** (`no-logic`) Conditionals, loops, computation, or branching in a
   test body mean the test itself is unverified code — use parametrization/fixtures instead.
5. **Fixture & factory design.** (`fixtures`) Duplication is removed via fixtures/factories,
   not copy-paste and not intent-hiding "helper" indirection that buries what's under test.
6. **Assertion quality.** (`assertions`) Assert on types/values, not brittle message
   substrings (unless the message *is* the contract); no over-assertion pinning irrelevant
   incidental state.
7. **Parametrization vs duplication.** (`parametrization`) Same behavior over many inputs →
   one parametrized test; *distinct* behaviors stay distinct tests (don't cram different
   specs into one).

### Strategy
8. **Over-mocking / mock-your-own-domain.** (`over-mock`) Needing to mock your own domain
   to test it is a design smell (missing port / DIP) — the test-side symptom of a
   production problem. File the fix under `solid`/`ddd` (hub); name the symptom here.
   Also: over-specified mock expectations (asserting internal call order) and tests that
   only assert the mock.
9. **Isolation.** (`isolation`) No shared mutable state or ordering dependency between
   tests; temp dirs over repo writes; clocks/env stubbed at the boundary and restored.
10. **Speed / markers.** (`speed`) Slow or integration tests are marked and separable from
    the fast unit run; the suite doesn't force everything through a slow path.

### Tending (the missing "clean up" motion — the suite only grows)
11. **Stale / redundant tests.** (`stale`) Detect, with strong evidence, tests that have
    outlived their purpose — the suite is never cleaned, so this is where the growth
    comes from:
    - **Dead** — reference symbols/modules/code paths that no longer exist (won't import,
      or pin a removed branch). Highest-confidence removal; often a collection error.
    - **Provably duplicate** — assert identical behavior on identical inputs (e.g. an old
      narrow test left beside a newer parametrized one that subsumes it).
    - **Obsolete** — pin behavior a refactor/feature intentionally removed or changed.
    - **Vacuous / tautological** — assert nothing meaningful, or only assert the mock.

    **Boundary:** a *behavior-preserving* refactor never orphans a test (behavior is
    preserved), so stale tests accumulate from behavior-*changing* work — this lens tends
    them regardless of which change created them.

## When NOT to flag (judgment, not dogma)

- **A flat file that's genuinely small and cohesive** doesn't need class/`describe`
  scaffolding — don't demand architecture a 40-line test file hasn't earned.
- **Integration/e2e tests legitimately touch several things** — "one behavior" is about
  unit tests; don't force an end-to-end flow into isolated micro-tests.
- **A "duplicate" you can't *prove* is redundant is not redundant.** If you cannot show
  (by coverage, see the deletion protocol) that removing a test loses no coverage, it
  stays. Suspicion is not evidence; deleting a real edge-case guard is worse than any
  duplication.
- **Some mocking is correct** — at true infrastructure boundaries (network, clock,
  filesystem). Only mocking *your own domain* is the smell.
- **Characterization pins can look odd** — a pin asserting an exact surprising value may
  be load-bearing (it documents current behavior deliberately). Flag, don't assume.
