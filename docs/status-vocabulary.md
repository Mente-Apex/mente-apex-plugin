# Report status vocabulary

**One closed vocabulary, used by every lens and by the cycle-gate.** A check that
did not run must never read as a check that found nothing.

Defined once here so the lenses reference it rather than each restating it.
Cited by [#121](https://github.com/menteapex/mente-apex-plugin/issues/121) and by
[`superpowers/specs/2026-08-02-cycle-gate-verdict-design.md`](superpowers/specs/2026-08-02-cycle-gate-verdict-design.md) §2.2.

## The four states

| Status | Meaning | In a report | At the cycle-gate |
|---|---|---|---|
| `ran` | executed fully; findings (or none) are real | record normally | passes |
| `degraded` | executed on a lower rung of the ladder, or on part of the target | record **which rung ran and what was skipped** | passes |
| `unverified` | did not execute — tool absent, language unsupported, agent failed, scope excluded it | record **with the reason** | passes |
| *silence* | nothing said, when the check was available | — | **blocks** |

## The two rules

1. **Absence is data, never silence.** A lens that errored, degraded, or found
   nothing is recorded in `## Coverage & method`. Omitting it is a defect, not a
   tidy report.
2. **`unverified` always carries a reason.** "Did not run" without a cause is
   indistinguishable from silence. The reason is what makes the gap actionable —
   and where a build could supply the missing tool, the reason carries the
   coordinates too (cycle-gate spec §4.5).

## Why `ran`-clean and `unverified` must not look alike

They mean opposite things and read identically to a human skimming:

- *"mutation score: —"* because nothing survived
- *"mutation score: —"* because mutation testing never ran

The first is evidence. The second is a hole. A report that cannot tell them
apart is worse than one that omits the section, because it invites a false
conclusion.

## Applies to

Every lens (`solid`, `gof`, `ddd`, `clean-architecture`, `clean-code`,
`test-quality`), the `code-quality` umbrella, and every measurement inside a
report — not just whole-lens outcomes. A single degraded measurement in an
otherwise clean lens is still `degraded`.
