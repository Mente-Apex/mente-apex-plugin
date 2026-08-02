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
over the refactored test:

    uv run python scripts/mutation_gate.py --repo-root . --scope working-tree

Exit `0` = looked, found nothing. `1` = survivors. `2` = could not verify the scope
(tool missing, backend crashed, baseline broken, zero mutants generated) — treat a `2`
as "the gate proved nothing", never as a pass, and say so rather than recording the
refactor as safe on the strength of it.

If the test under audit appears in a survivor's `associated_tests`, the refactor
hollowed it out — a mutant it should have killed is still alive. Revert the
refactor and report it. Record the gate result in the safety clause of the
apply-log line, quoting the mutant.

The manual loop — break the code under test by hand, confirm the test fails,
restore — remains the documented **fallback** for anything the gate cannot reach:
a repo with no mutation tool declared, an unsupported language, or a guard with
no marker. The automated gate is the sweep; the manual one is the spot check.

## Gate B — deleting a stale test (the inverse gate)

**Never auto-delete.** A deletion is applied only with the reviewer's **coverage proof**
in hand, and you re-confirm it: capture SUT coverage, remove the test, re-run coverage, and
confirm the lines/branches it *uniquely* covered are still covered (or the tested code is
itself gone — a dead test). If coverage drops, **abort the deletion** — the test was the
sole guard of that path; mark the rec `skipped` with that reason and leave it in the report
as "keep". **Prefer merge over delete**: if the rec is "fold narrow test into a parametrized
case", that is a Gate-A refactor (with the mutation gate on the merged case), not a deletion.
Record the coverage result in the safety clause.

## Hard rules

- One rec at a time; a fresh clean tree per job (the orchestrator checkpoint-commits each
  verified rec on the working branch). Do not commit yourself.
- **High risk** (de-mocking that changes a seam, deleting anything you had to reason hard
  about, touching the safety net) → explicit per-rec confirmation first; when in doubt,
  leave it advisory.
- Update only the touched recs' Status lines and the Apply log; the report is otherwise
  the reviewer's. Anything noticed but not touched goes in your yield-back summary.
