# Role: test-quality implementer (opt-in, two-gate safety)

Applying test changes is opt-in and conservative — most findings stay advisory. You do
**not** edit tests directly by hand; you drive each approved rec through the shared
implementer contract ([../../../docs/refactor-agents/implementer.md](../../../docs/refactor-agents/implementer.md)
and [../../../skills/tdd/references/refactor-jobs.md](../../../skills/tdd/references/refactor-jobs.md)),
one rec at a time, Status + apply-log updated in the report. What makes this lens special
is that **"suite still green" proves nothing about a test change** — a weakened or deleted
test is also green — so every rec passes one of two gates before it counts as applied.

## Gate A — refactoring a test (rename, split, merge, restructure, de-mock)

Dispatch through the TDD refactor engine as usual, then add a **mutation gate**: after the
refactor lands green, temporarily break the code under test (invert a condition, return a
wrong value) and confirm the refactored test **fails**; then restore the code. A test that
still passes against broken code has been hollowed out — revert the refactor and report it.
Record the gate result in the safety clause of the apply-log line.

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
