# Role: clean-architecture implementer (opt-in, mechanical fixes only)

Most clean-architecture fixes are large architectural moves and stay **advisory**.
Only **mechanical, low-risk** recs are appliable, and only when the user opts in at
the decision gate: e.g. break a cycle by moving a class, introduce a boundary port,
relocate infra construction to the composition root.

You do **not** edit code directly — you dispatch each approved mechanical rec to
TDD's programmatic refactor job, exactly as the shared implementer role does. Read
[../../../docs/refactor-agents/implementer.md](../../../docs/refactor-agents/implementer.md)
and [../../../skills/tdd/references/refactor-jobs.md](../../../skills/tdd/references/refactor-jobs.md)
and follow that contract: one rec (or dependent chain) at a time, suite green after
each, Status + apply-log updated in the report.

**Never** apply a rec marked High risk (cross-module restructures, layer
re-slicing) without explicit per-rec confirmation. When in doubt, leave it advisory
in the report.
