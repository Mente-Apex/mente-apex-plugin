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
what the gate is built around: `mutmut` for Python, Stryker for JS/TS — both mature, both
associating survivors with tests, though at different granularities (see the spike findings).

This plugin repo is unusual: much of its suite asserts over **Markdown**, because its product
*is* Markdown. That case gets a backend (below), and it is the case this repo will exercise
first — but it is an adapter for documentation-as-code suites, not the point of the work. Any
design decision that helps the prose backend at the cost of the code path is the wrong trade.

## Shape

`scripts/mutation_gate.py` — a selector, a set of backends, a merged report. Two callers.

The **backend contract is deliberately narrow**, because the two mature tools already do the
mutating themselves:

    backend.survivors(selection) -> [Survivor]

Given a selection of files and tests, a backend returns survivors. *How* it gets them is its
own business — `mutmut` and Stryker are invoked and their output parsed; only the prose backend
generates and applies mutants itself. An earlier draft put mutant generation in the executor,
which left nowhere to plug the real tools in.

    Survivor(artifact, location, mutant_description, associated_tests, backend, tier)

Every backend fills the same shape, so the gate merges results into one list and the operator
never reconciles two tools' output.

### Selection and dispatch

The gate **partitions the selection by stack, then invokes each backend once over its
partition** — not once per test. `mutmut` and Stryker are invoked per project/file set; a
per-test invocation loop would be ruinously slow and is explicitly not the design.

- **Python files** → `mutmut` over that partition.
- **JS/TS files** → Stryker over that partition, under fnm-selected Node.
- **Prose artifacts with a declared slice** → the built-in prose backend below.
- **Anything left over** → reported as *not verifiable*, never silently passed.

**Mixed repos are normal** — a Python API with a TypeScript frontend is the common shape, and
one audit runs both partitions in the same pass. A repo with no JS is simply a run where the
Stryker partition is empty.

Dispatch is a strategy seam, not an if-chain — a fourth backend must be additive.

### Survivor policy

No score threshold; a threshold gets gamed and "87%" tells an operator nothing.

A survivor **blocks** when the test under audit is among the survivor's `associated_tests` —
i.e. the test that should have killed this mutant did not. Everything else is advisory,
reported and not enforced.

**The granularity of "associated" is the backend's, and it differs** (see the spike below):
Stryker reports per-test coverage, while `mutmut` associates tests with the mutated *function*,
not the line. The gate takes what the backend gives and states which it used in the report,
rather than pretending to a precision it does not have.

Reporting names the test and the mutant, as a diff where the backend provides one: *"inverting
`and` → `or` at `money.py:2` leaves `test_member_over_threshold_gets_ten_percent_off` green"*.
Never a percentage.

### Runtime and isolation

Full-suite mutation is far too slow for an interactive skill. Default scope is **the files
changed against the merge-base with the repo's default branch** — the same diff the rest of the
plugin reasons about, not the working-tree diff, so a sweep is stable across intermediate
commits. Working-tree scope and full-repo scope are explicit flags. Both tools support
file-scoped runs natively, so this is configuration, not extra machinery.

**Mutation writes to the tree**, which the audited repo's operator did not ask for: `mutmut`
materialises a `mutants/` directory, Stryker a `.stryker-tmp/`, and the prose backend edits the
artifact in place. So the gate **runs against a scratch copy** — a `git worktree` at the audited
commit where one is available, a temp-dir copy otherwise. The operator's tree is never touched,
a dirty tree is safe, and the sweep does not block them from working. The prose backend
additionally restores via `try/finally` over the original text held in memory, never a git
operation, so an abort inside the scratch copy still leaves it consistent.

**Runaway mutants.** A mutant can turn a loop infinite. Both tools apply a per-mutant timeout
derived from the clean run; the gate surfaces timed-out mutants as their own category —
neither killed nor survived — because silently counting them either way is a lie. Flaky tests
are the same class of problem, amplified: a test that fails intermittently produces phantom
kills, so the gate records the clean-run baseline and flags any test that failed *before* any
mutant was applied.

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

- A survivor whose `associated_tests` include a test under audit → a **rubric-11 tending
  finding** ("vacuous test").
- A prose guard with no marker → a **Minor** ("unverifiable by construction").
- A timed-out or flaky-baseline mutant → **neither**; it is reported as inconclusive, with the
  test named, so nobody reads silence as a pass.

Survivors land **in the report**, not in stdout: `references/report-template.md` gains a
Mutation-gate section carrying the survivor list, the scope that produced it (diff or full),
the granularity each backend supplied, and any *not available* / inconclusive entries. This
lens already holds that the report is the single source of truth; a gate that reports elsewhere
would break that.

The analyzer stays read-only **with respect to the operator's tree** — all mutation happens in
the scratch copy — and read-only in the usual sense too: it runs the gate, it does not act on
the result. The reviewer
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

The script ships with the plugin, so it always exists. Everything else is detected and
degrades, per the provisioning contract above:

- **Python-only repo** → mutmut backend; Stryker selects nothing.
- **JS/TS-only repo** → Stryker backend; mutmut selects nothing.
- **Mixed repo** → both, in one pass, merged into one survivor list.
- **Tool missing for a stack that is present** → *not available for `<language>`*, with the
  declared-install command offered as an opt-in. The audit continues.
- **No markers** → the code path is entirely unaffected; prose guards, if any, report as
  unverifiable.

The lens changes the audited repo's test configuration only on explicit opt-in, and only the
provisioning it offered. In this repo, marker adoption is incremental: undeclared guards are a
Minor finding, not a backfill.

## Testing the harness

Unit tests over fixture projects in `tmp_path`: a tiny module with a sound test and a vacuous
one, asserting the sound one is **killed** and the vacuous one **survives** — known-good and
known-bad specimens, which is the honest way to test a mutation tool. Self-application is not.
Same pair for the prose backend over a fixture Markdown file.

Backend dispatch is tested against fakes so the suite does not depend on `mutmut` or Stryker
being installed — including the cases that matter most for generality: a Python-only tree, a
JS-only tree, a **mixed tree** (asserting both backends select and the results merge into one
list), and a stack present with its tool absent (asserting *not available* plus the right
install command, and that the audit continues). Parsing gets pinned against **captured real
output** from the spike — `mutmut-stats.json` and a Stryker `mutation.json` — so a schema change
in either tool fails loudly here rather than silently reporting nothing.

Two safety properties get their own tests: the operator's tree is **byte-identical after a run**
(including a run aborted mid-way), and the prose backend's `try/finally` restore holds when the
runner raises.

## Toolchain provisioning — in the audited repo

The tools are dependencies **of the codebase being audited**, not of this plugin. The plugin
ships no mutation engine; it detects what the audited repo needs and helps that repo declare
it. Same contract per language:

| Stack | Detected by | Declared with | Runner |
|---|---|---|---|
| Python | `pyproject.toml` / a pytest suite | `uv add --dev mutmut` | `uv run` |
| JS/TS | `package.json` / a Vitest or Jest suite | `npm install -D @stryker-mutator/core` plus the runner plugin (`@stryker-mutator/vitest-runner` or `-jest-runner`) | `npx`, under fnm-selected Node |

Rules that hold for both, and for any backend added later:

- **Declared, never ambient.** No bare `pip install`, no global `npm -g`, no hand-activated
  `.venv`, no system Node. A tool the environment needs but does not declare is a bug — a
  rebuild silently drops it.
- **Never installed behind the operator's back.** Missing tool → the gate reports *not
  available for `<language>`* and offers the exact declared-install command for that repo, as
  an opt-in. The audit continues without it; a missing tool degrades the run, it never fails
  it.
- **Config generation is part of provisioning.** `mutmut` reads `pyproject.toml` and largely
  works from an existing pytest setup; Stryker needs a `stryker.conf.json` naming the test
  runner and the mutate glob, and most repos have none. A repo adopting the JS backend gets a
  minimal generated config alongside the install command — otherwise "install Stryker" is
  advice that does not produce a working run.
- **A mixed repo provisions both**, independently. Python present and JS absent is not a
  failure state; neither is the reverse.

For this plugin's own suite: `uv add --dev mutmut`, no Stryker (there is no JS/TS here).

## Spike findings (both tools actually run)

Run 2026-07-29 against throwaway projects — the same `discount(total, is_member)` function with
one sound test and one vacuous `assert result is not None` guard — to settle what the backends
really give the gate. Both killed the sound assertions and left the vacuous guard unpunished,
which is the behaviour the whole design rests on.

**`mutmut` 3.6.0, Python 3.14.6, under `uv run`.** Installs and runs clean; the 3.14 risk is
closed. Notes that change the implementation:

- The config key is **`source_paths`** — `paths_to_mutate` is accepted but deprecation-warns.
- It materialises a **`mutants/` directory in the project**, confirming the scratch-copy rule.
- Association is **function-level**: `mutants/mutmut-stats.json` carries
  `tests_by_mangled_function_name`, mapping the mutated function to the pytest node ids that
  exercise it. There is **no `killedBy` and no per-line mapping.**
- `mutmut results` lists survivors by mangled name; `mutmut show <id>` yields a unified diff —
  that is the reporting material.

**Stryker `@stryker-mutator/core` + `vitest-runner`, Node v24.18.0 via fnm.** Richer, and the
JSON report is the integration surface (`reports/mutation/mutation.json`, `schemaVersion` 1.0):

- Per mutant: `status`, `mutatorName`, `replacement`, `statusReason`, **`killedBy`**,
  **`coveredBy`**, and a precise `location` (line **and** column).
- `testFiles[].tests[]` resolves those ids to test names.
- Timeouts are a first-class status, matching the runaway-mutant category above.
- Needs a `stryker.conf.json` with `testRunner`, `mutate`, and `coverageAnalysis: "perTest"` —
  `perTest` is what produces `coveredBy` at all, so the generated config must set it.

**Consequence for the design.** The asymmetry is real and permanent: Stryker answers "which
test failed to kill this line", `mutmut` answers "which tests touch this function". The
survivor policy is written to the weaker of the two and the report states which granularity
produced each finding. A `mutmut` survivor therefore reads as *"a mutant in `discount()`
survived; these tests exercise it"* — still enough to name a vacuous guard, which is the job.

Spike projects live under the session scratchpad; they are evidence, not artifacts to commit.

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
