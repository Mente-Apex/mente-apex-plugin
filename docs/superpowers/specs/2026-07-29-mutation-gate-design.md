# test-quality mutation gate — design

Issue: #113. Touches `skills/test-quality/` and adds `scripts/mutation_gate.py`.

## Problem

`/test-quality`'s mutation gate is prose, not machinery. `skills/test-quality/SKILL.md:79-82`
and `skills/test-quality/agents/implementer.md:11-17` both say: after a refactor lands green,
temporarily break the code under test, confirm the test fails, restore. The idea is right —
"suite still green" proves nothing when the thing you changed *is* the test — but no tool is
named, the mutant is whatever the operator thinks of, and the evidence is a pasted terminal
transcript. It is unrepeatable, and it only ever runs on a test somebody already suspected.

The live case is `design/release-two-axis-adapters`, where three plan-specified tests turned
out to be vacuous guards, each passing for a reason unrelated to the property it named:

| Task | Test | Why it asserted nothing |
|---|---|---|
| 2 | selector-syntax, placeholder-vocabulary, optional-marker guards | Iterated `adapter_files()` only; the fields they validated had moved to `references/distributions/`, so the guards ran over a file set that no longer used them |
| 7 | `test_gate_relock_and_build_run_per_component` | Windowed ±400 chars around the *first* occurrence of `gate_command`, which sits in Step 0's field list ~2400 chars from Step 2 — deleting Step 2's loop entirely left it green |
| 8 | `test_step_three_checks_every_component_manifest_against_the_canonical_version` | Whole-file substring search; two of three assertions passed against the file *before* the commit meant to satisfy them |

All three were caught by a human reasoning it out, or by an implementer manually deleting the
behaviour. All three were **born vacuous** — none had been refactored, so none would ever have
reached the existing gate.

## The decision that shapes everything else: prose first

Issue #113 names `mutmut` and Stryker. Both mutate *source*. All three motivating failures
assert over **Markdown** — neither tool would have caught any of them, and this repo's suite is
dominated by that shape (`tests/test_*_skill_structure.py`). So the design's weight goes on
mutating the **artifact under test**, whatever its shape, with the code tools as one backend
among several rather than as the point.

`extract_section()` already exists in `tests/test_code_quality_skill_structure.py:22`,
duplicated across guard files. The section-slicing convention emerged organically under
exactly the pressure this design formalises; the design absorbs it rather than reinventing it.

## Shape

Three pieces, each usable without the others.

### a. The `covers` marker

    @pytest.mark.covers("skills/test-quality/SKILL.md", section="Applying is guarded by two gates")

A test declares the artifact slice it guards. Registered under `[tool.pytest.ini_options]
markers` in `pyproject.toml`, resolved by a helper in `tests/conftest.py`.

The marker is **also what the test reads**: the guard asks the helper for its slice instead of
re-implementing `extract_section`, so the declaration and the assertion cannot drift apart.
This is what kills the Task 7/8 bug class *by construction* — a test can no longer window a
region other than the one it declared, because there is only one region and it is named.

### b. `scripts/mutation_gate.py`

The executor. Given a test selection it collects targets from markers and, for each:

    mutate the slice → run just that test → record survived/killed → restore

Restore is a `try/finally` over the original text held in memory. Never a git operation: the
harness must be safe to run on a dirty tree, and a `git checkout` would eat unrelated work.

### c. Backend dispatch

- Marker pointing at a `.md` (or any prose artifact) → the prose mutators below.
- No marker, test exercises real source → `mutmut` (Python) / Stryker (JS/TS), scoped to the
  diff.
- No marker and no source target → **not verifiable**, reported as such.

One implementation; the analyzer and the implementer are two callers of it.

## The prose mutators

Applied to the declared slice only, never the whole file.

1. **Delete the slice.** The blunt one. The test must fail. Catches Task 2 and Task 7 — a
   guard whose region no longer exists, or that never read the region it named.
2. **Blank the slice.** Replace the body with a placeholder, keep the heading. Separates "the
   test needs the heading" from "the test needs the content"; a survivor is asserting on
   structure it did not mean to.
3. **Invert directives.** Swap imperative polarity inside the slice (`MUST` ↔ `MUST NOT`,
   `never` ↔ `always`, `Do NOT` ↔ `Do`). Catches Task 8's class — a guard confirming a word is
   *present* without confirming what it says.

A survivor under any operator is a finding. Operator 3 is the noisy one: it can legitimately
survive when a test genuinely only checks presence, so its survivors report at a lower tier and
must name the specific inversion that made no difference.

**Reporting is never a score.** Per the issue, each survivor reads as the assertion and the
mutation — *"deleting `SKILL.md` § Step 2 leaves `test_gate_relock_and_build_run_per_component`
green"* — not "87%".

## The two callers

### Analyzer (Phase 1) — the sweep

Scoped to the diff by default: tests whose file changed, or whose declared artifact changed.
Full-suite is an explicit opt-in flag, because it is the slow one and an interactive skill
cannot afford it by default.

- A survivor becomes a **rubric-11 tending finding** ("vacuous guard").
- An undeclared prose guard becomes a **Minor** ("unverifiable by construction").

The analyzer stays read-only — it runs the script, it does not act on the result. The reviewer
re-verifies every survivor against the real test before it reaches the report, exactly as with
every other finding in this lens.

This is the half that catches born-vacuous tests, which is where all three real cases came
from.

### Implementer (Gate A) — the per-rec gate

Replaces the hand-waved "temporarily break the code under test" with a call to the script,
scoped to the one test just refactored. Survived → the refactor hollowed the test → revert and
report. That is already the rule; this makes it mechanical.

**The manual delete-and-confirm loop stays documented** as the fallback for anything the script
cannot reach. In a foreign repo with no markers it is all there is, and the issue is explicit
that it must survive: the automated gate is the sweep, the manual one is the spot check.

### Survivor policy

No score threshold — a threshold gets gamed. A survivor **blocks** only when it is on the slice
the test declared it covers. Everything else is advisory.

Gate B (coverage-non-regression for deletions) is untouched by this work.

## Reach into foreign repos

`/test-quality` audits any codebase, and a marker convention only exists where it has been
adopted. So: the **script ships with the plugin** and therefore always exists; the **marker is
optional**. In a marker-less repo the harness still dispatches source-shaped tests to
`mutmut`/Stryker, and reports the prose guards as unverifiable rather than failing. The lens
does not edit the audited repo's test configuration.

Adoption in *this* repo is incremental: undeclared guards are a Minor finding, not a backfill.
The debt stays visible without attaching a large mechanical diff to the mechanism.

## Testing the harness

Ordinary unit tests over fixture artifacts in `tmp_path`: a fixture Markdown file plus a
deliberately-vacuous test and a deliberately-sound one, asserting the sound one is **killed**
and the vacuous one **survives**. Known-good and known-bad specimens is the honest way to test
a mutation tool; self-application is not.

Restore-on-failure gets its own test: raise mid-run, assert the artifact is byte-identical
afterwards.

## Dependencies

- `uv add --dev mutmut` — declared, never ambient, never bare `pip install`.
- **Risk to settle in task 1:** this repo is `requires-python = ">=3.14"` and mutmut's support
  there is unverified. If it does not run, the Python backend degrades to "not available,
  reported as such" and the prose path — the value here — is unaffected. The design does not
  depend on mutmut working.
- Stryker is **not** added: there is no JS/TS in this repo, so the skill detects and instructs
  rather than shipping a dependency nobody uses. Under fnm-selected Node wherever it does run.

## Verification gates

Not optional; each is its own task with evidence pasted into the plan.

- **`/solid`** on `scripts/mutation_gate.py`. It is the first script here with real internal
  structure (collector / mutator / runner / reporter), and the prose-vs-mutmut-vs-Stryker
  dispatch is a strategy seam — if it lands as an if-chain the third backend will hurt.
  Analyzer + reviewer pass, findings applied through TDD.
- **`/skill-creator`** evals on the changed `test-quality` SKILL.md and agent prompts. The
  trigger surface shifts (the analyzer now runs a sweep, the implementer now calls a script),
  so the description and agent contracts need evals, not just edits — as with the existing
  analyzer contract pins in `tests/`.
- The existing suite green.

## Out of scope

- Backfilling markers across the existing suite — it is a finding, not a diff.
- Gate B (coverage-non-regression).
- CI wiring.
- Any change to production `scripts/` behaviour beyond what the harness itself needs.
