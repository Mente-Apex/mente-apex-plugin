# test-quality mutation gate — design

Issue: #113. Touches `skills/test-quality/` and adds `scripts/mutation_gate.py`.

## Problem

`/test-quality`'s mutation gate is prose, not machinery. `skills/test-quality/SKILL.md:79-82`
and `skills/test-quality/agents/implementer.md:11-17` both say: after a refactor lands green,
temporarily break the code under test, confirm the test fails, restore. The idea is right —
"suite still green" proves nothing when the thing you changed *is* the test — but no tool is
named, the mutant is whatever the operator thinks of, and the evidence is a pasted terminal
transcript. It is unrepeatable, and it only ever runs on a test somebody already suspected.

The lens needs the standard answer to that problem, which is **mutation testing**: change the
code under test in small, mechanical ways and see whether the suite notices. A test that
passes against deliberately broken code is not a test.

## Scope: this is a general code-mutation gate

`/test-quality` audits any codebase, and in almost every one of them the suite exercises
**real source** — Python functions, TypeScript modules. That is the primary case and it is
what the gate is built around: `mutmut` for Python, Stryker for JS/TS, both mature, both
producing a mutant→covering-test mapping the lens can read.

This plugin repo is unusual: much of its suite asserts over **Markdown**, because its product
*is* Markdown. That case gets a backend (below), and it is the case this repo will exercise
first — but it is an adapter for documentation-as-code suites, not the point of the work. Any
design decision that helps the prose backend at the cost of the code path is the wrong trade.

## Shape

`scripts/mutation_gate.py` — one executor, several backends, two callers.

    select tests → pick backend → generate mutants → run the covering tests
                 → record survived/killed → restore → report survivors

Restore is a `try/finally` over the original text held in memory, never a git operation: the
harness must be safe on a dirty tree, and a `git checkout` would eat unrelated work. (`mutmut`
and Stryker each manage their own workspace; the same guarantee is asserted by test.)

### Backend dispatch

The gate picks by what the selected tests actually exercise:

- **Python source** → `mutmut`, scoped to the changed files.
- **JS/TS source** → Stryker, scoped to the changed files, under fnm-selected Node.
- **Prose artifact** → the built-in prose backend below.
- **Nothing resolvable** → reported as *not verifiable*, never silently passed.

The dispatch is a strategy seam, not an if-chain — a fourth backend must be additive.

### Survivor policy

No score threshold; a threshold gets gamed and "87%" tells an operator nothing. A survivor
**blocks** only when it lands on a line the changed test is recorded as covering — that is the
signal worth stopping on. Everything else is advisory noise, reported and not enforced.

Reporting names the assertion and the mutant: *"inverting the condition at `foo.py:41` leaves
`test_rejects_expired_token` green"*. Never a percentage.

### Runtime

Full-suite mutation is far too slow for an interactive skill. Default scope is **the files in
the diff**; full-repo is an explicit opt-in flag. Both backends support file-scoped runs
natively, so this is configuration, not extra machinery.

## The prose backend

For suites whose subject is a document. Without it, a repo like this one gets no gate at all,
because neither tool will mutate a Markdown heading.

The unit is a **declared slice**. Where `mutmut` and Stryker derive the mutant→test mapping
from coverage, prose has none, so the test declares its target:

    @pytest.mark.covers("skills/test-quality/SKILL.md", section="Applying is guarded by two gates")

The marker is **also what the test reads** — the guard asks a `conftest.py` helper for its
slice rather than re-implementing section extraction, so declaration and assertion cannot
drift apart. `extract_section()` already exists in
`tests/test_code_quality_skill_structure.py:22`, duplicated across guard files; the helper
absorbs it.

Three operators, applied to the declared slice only:

1. **Delete the slice** — the blunt one; the test must fail.
2. **Blank the slice** — replace the body, keep the heading. Separates "needs the heading" from
   "needs the content".
3. **Invert directives** — `MUST` ↔ `MUST NOT`, `never` ↔ `always`, `Do NOT` ↔ `Do`. Catches a
   guard that confirms a word is *present* without confirming what it says.

Operator 3 can legitimately survive when a test genuinely only checks presence, so its
survivors report at a lower tier and must name the inversion that made no difference.

The marker is **prose-only and optional**. Code-shaped tests need no annotation, and a repo
that has adopted no markers still gets the full code gate.

### Why this repo needs it

On `design/release-two-axis-adapters`, three plan-specified tests were vacuous guards, each
passing for a reason unrelated to the property it named:

| Task | Test | Why it asserted nothing |
|---|---|---|
| 2 | selector-syntax, placeholder-vocabulary, optional-marker guards | Iterated `adapter_files()` only; the fields they validated had moved to `references/distributions/` |
| 7 | `test_gate_relock_and_build_run_per_component` | Windowed ±400 chars around the *first* occurrence of `gate_command`, ~2400 chars from the section it meant to check — deleting that section left it green |
| 8 | `test_step_three_checks_every_component_manifest_against_the_canonical_version` | Whole-file substring search; two assertions passed against the file *before* the commit meant to satisfy them |

Operator 1 kills Task 2 and 7; operator 3 kills Task 8. The declared-slice rule kills the 7/8
class outright by construction — a test can no longer window a region other than the one it
named.

## The two callers

### Analyzer (Phase 1) — the sweep

Runs the gate over the diff and turns survivors into findings:

- A survivor on a covered line → a **rubric-11 tending finding** ("vacuous test").
- A prose guard with no marker → a **Minor** ("unverifiable by construction").

The analyzer stays read-only — it runs the gate, it does not act on the result. The reviewer
re-verifies every survivor against the real test before it reaches the report, as with every
other finding in this lens.

This half is what catches **born-vacuous** tests. All three cases above were never refactored,
so none would have reached a post-refactor gate; discovery, not just verification, is where
the value is.

### Implementer (Gate A) — the per-rec gate

Replaces the hand-waved "temporarily break the code under test" with a call to the gate, scoped
to the one test just refactored. Survived → the refactor hollowed the test → revert and report.
That is already the rule; this makes it mechanical.

**The manual delete-and-confirm loop stays documented** as the fallback for anything the gate
cannot reach — a repo with no mutation tool installed, or an unsupported language. The
automated gate is the sweep; the manual one is the spot check.

Gate B (coverage-non-regression for deletions) is untouched by this work.

## Reach into foreign repos

The script ships with the plugin, so it always exists. Everything else degrades:

- Tool missing → the gate reports *not available* for that language and the audit continues.
  It never fails the run for a tool the user has not installed, and it never installs one
  behind their back.
- No markers → the code path is unaffected; prose guards report as unverifiable.

The lens does not edit the audited repo's test configuration. In this repo, marker adoption is
incremental: undeclared guards are a Minor finding, not a backfill.

## Testing the harness

Unit tests over fixture projects in `tmp_path`: a tiny module with a sound test and a vacuous
one, asserting the sound one is **killed** and the vacuous one **survives** — known-good and
known-bad specimens, which is the honest way to test a mutation tool. Self-application is not.
Same pair for the prose backend over a fixture Markdown file.

Backend dispatch is tested against fakes so the suite does not depend on `mutmut` or Stryker
being installed. Restore-on-failure gets its own test: raise mid-run, assert the artifact is
byte-identical afterwards.

## Dependencies

- `uv add --dev mutmut` — declared, never ambient, never bare `pip install`.
- **Risk to settle in task 1:** this repo is `requires-python = ">=3.14"` and mutmut's support
  there is unverified. If it does not run here, the Python backend still ships (it is the
  primary path for the repos the lens audits) and this repo's own gate leans on the prose
  backend. Confirm before building on it.
- Stryker is **not** added as a dependency: there is no JS/TS here. The skill detects it in the
  audited repo and instructs; wherever it runs, it runs under fnm-selected Node, never system
  Node.

## Verification gates

Not optional; each is its own task with evidence pasted into the plan.

- **`/solid`** on `scripts/mutation_gate.py`. It is the first script here with real internal
  structure (selector / backend / runner / reporter), and the backend dispatch is exactly the
  seam that hurts when it lands as an if-chain. Analyzer + reviewer pass, findings applied
  through TDD.
- **`/skill-creator`** evals on the changed `test-quality` SKILL.md and agent prompts. The
  trigger surface shifts (the analyzer now runs a sweep, the implementer now calls a script),
  so the description and agent contracts need evals, not just edits — as with the existing
  analyzer contract pins in `tests/`.
- The existing suite green.

## Out of scope

- Backfilling markers across this repo's existing suite — it is a finding, not a diff.
- Gate B (coverage-non-regression).
- CI wiring.
- Any change to production `scripts/` behaviour beyond what the harness itself needs.
