# Java 25 probe fixtures

Regression net for the complexity probe's Java support, per
`docs/superpowers/specs/2026-08-02-cycle-gate-verdict-design.md` §6.

These exist to answer one question: **can the probe still parse this language?**
They are not a style reference and are not compiled by any build.

| File | Construct under test | JEP |
|---|---|---|
| `Shape.java` | `sealed interface`, `record`, pattern-matching `switch` with `when` guards | 409, 395, 441 |
| `Compact.java` | compact source file — instance `void main()`, `import module java.base`, `IO.println` | 511, 512 |
| `Flexible.java` | flexible constructor bodies — validation before `this.` assignment | 513 |

## Verified baseline (lizard 1.23.0, 2026-08-02)

| Function | NLOC | CCN |
|---|---|---|
| `AreaCalculator::area` | 9 | 6 |
| `main` | 11 | 7 |
| `Account::Account` | 10 | 4 |

**Known inaccuracy:** `AreaCalculator::area` has five `case` arms and two `when`
guards, so its true cyclomatic complexity is 8, not 6 — lizard does not count
pattern guards. Harmless by construction, because numbers never decide a gate
verdict (spec §5.1); recorded so it is not rediscovered as a bug.

A change in these numbers means the probe's parsing changed. Investigate before
updating the table.
