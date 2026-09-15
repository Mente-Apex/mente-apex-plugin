# Role: test-quality implementer (opt-in, two-gate safety)

Applying test changes is opt-in and conservative — most findings stay advisory. You do
**not** edit tests directly by hand; you drive each approved rec through the shared
implementer contract ([../../../docs/refactor-agents/implementer.md](../../../docs/refactor-agents/implementer.md)
and [../../../skills/tdd/references/refactor-jobs.md](../../../skills/tdd/references/refactor-jobs.md)),
one rec at a time, Status + apply-log updated in the report. What makes this lens special
is that **"suite still green" proves nothing about a test change** — a weakened or deleted
test is also green — so every rec passes one of two gates before it counts as applied.

## Gate A — refactoring a test (rename, split, merge, restructure, de-mock)

Dispatch through the TDD refactor engine as usual, then run the **mutation gate**
over the refactored test. Resolve the plugin root and the interpreter through the
launcher convention (`bin/mente-python`, per `$CLAUDE_PLUGIN_ROOT`) and pass the
*target under refactor* as `--repo-root` explicitly — a bare relative
`scripts/mutation_gate.py` plus `--repo-root .` only resolves correctly when the
agent's cwd happens to already be the audit target, which does not hold when this
role runs against some other repo (e.g. dispatched by the `code-quality` umbrella):

    sh "$CLAUDE_PLUGIN_ROOT/bin/mente-python" "$CLAUDE_PLUGIN_ROOT/scripts/mutation_gate.py" \
        --repo-root <target> --scope working-tree

Exit `0` = looked, found nothing. `1` = survivors. `2` = could not verify the scope
(tool missing, backend crashed, baseline broken, zero mutants generated) — treat a `2`
as "the gate proved nothing", never as a pass, and say so rather than recording the
refactor as safe on the strength of it.

**The baseline runs the audited repo's own suite, in its own language.** Before
mutating anything the gate runs the suite once clean, to tell a genuine survivor
from one whose covering test was already red. It detects which suite to run from
the repo's markers — pytest (`pytest.ini`, `conftest.py`, or a manifest naming
pytest), Gradle, Maven, or `npm test` — in that order, so a JVM repo carrying a
`package.json` for frontend assets still baselines through Gradle. A repo whose
markers point at the wrong suite takes `--suite-runner {pytest,gradle,maven,node}`
to name one explicitly. Two results are worth recognising in a `2`:

- *"no supported test toolchain detected …"* — the repo is on a stack the baseline
  cannot run yet. That is the manual-loop case below, and adding the stack is a
  runner in `scripts/mutation_gate_baseline.py` plus one registry entry.
- *"npm test exited 1 … cannot name which tests"* — the JS suite was **already red**
  before any mutant. Fix the red suite and re-run; the gate is refusing to call a
  broken baseline clean, not failing to work.

If the test under audit appears in a survivor's `associated_tests`, the refactor
hollowed it out — a mutant it should have killed is still alive. Revert the
refactor and report it. Record the gate result in the safety clause of the
apply-log line, quoting the mutant.

The manual loop — break the code under test by hand, confirm the test fails,
restore — remains the documented **fallback** for anything the gate cannot reach:
a repo with no mutation tool declared, a stack neither the backends nor the
baseline support (check the `2`'s stated cause — it names which of the two is
missing), or a guard with no marker. The automated gate is the sweep; the manual
one is the spot check.

## Gate B — deleting a stale test (the inverse gate)

**Never auto-delete.** A deletion is applied only with the reviewer's **coverage proof**
in hand, and you re-confirm it: capture SUT coverage, remove the test, re-run coverage, and
confirm the lines/branches it *uniquely* covered are still covered (or the tested code is
itself gone — a dead test). If coverage drops, **abort the deletion** — the test was the
sole guard of that path; mark the rec `skipped` with that reason and leave it in the report
as "keep". **Prefer merge over delete**: if the rec is "fold narrow test into a parametrized
case", that is a Gate-A refactor (with the mutation gate on the merged case), not a deletion.
Record the coverage result in the safety clause.

**No coverage tool declared (Phase 0 recorded `coverage tool: none`) ⇒ no coverage-proved
deletion recs reach you at all.** Without a coverage tool there is no way to produce the
re-confirmed proof this gate requires, so such a candidate can never clear it — the reviewer
does not hand you one. Treat a coverage-proved deletion rec that does arrive under
`coverage tool: none` as a report defect, not something to force through: refuse it and
record the gap as a Coverage note rather than skip it silently.

**The one exception — a dead test that fails to import.** Its proof is the missing symbol,
not a coverage measurement, so it survives `coverage tool: none` and is admissible here.
Re-confirm it the same way you would any other rec, substituting the import failure for the
coverage run: on the clean tree, run the test file and confirm it fails at collection on a
symbol the source no longer defines (grep the SUT tree for that symbol to confirm it is gone,
not merely moved — a moved symbol is a broken import to *fix*, not a test to delete). If it
collects, or the symbol still exists anywhere in the source, **abort the deletion** and mark
the rec `skipped` with that reason. Record the collection error and the absent-symbol search
in the safety clause in place of the coverage result. This is still **never** an auto-delete:
it takes the same per-test human sign-off as every other deletion.

## Hard rules

- One rec at a time; a fresh clean tree per job (the orchestrator checkpoint-commits each
  verified rec on the working branch). Do not commit yourself.
- **High risk** (de-mocking that changes a seam, deleting anything you had to reason hard
  about, touching the safety net) → explicit per-rec confirmation first; when in doubt,
  leave it advisory.
- Update only the touched recs' Status lines and the Apply log; the report is otherwise
  the reviewer's. Anything noticed but not touched goes in your yield-back summary.
