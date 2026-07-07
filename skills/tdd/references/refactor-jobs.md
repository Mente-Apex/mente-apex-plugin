# Programmatic refactor jobs

A **refactor job** is TDD's third programmatic entry (alongside feature and
legacy work): a *behavior-preserving structural change under a green safety
net*. It exists so other skills — `solid`, `gof` — apply their approved
recommendations through one engine instead of each re-implementing "apply,
run suite, revert on red." It is additive: feature and legacy contracts are
unchanged.

## Calling contract (stable — callers depend on it)

Input (from a lens's implementer-coordinator):
- `targets` — files/symbols the change touches
- `change` — the exact behavior-preserving restructuring (a rec's Proposed change)
- `test_command` + `baseline_status` — green, or the tolerated pre-existing failures
- `coverage` — `covered` if the suite exercises the targets, else `none`
- `new_behavior` — optional: any genuinely-new behavior the change introduces

Execution:
1. Safety net. `coverage == none` → run legacy mode: write characterization
   pins asserting what the code does today, to green. `covered` → use the
   existing suite. If current behavior looks wrong, flag it — never silently
   "fix" it; the oddity may be load-bearing.
2. Apply the smallest faithful version of `change`. Behavior-preserving; house
   style; descriptive names; no new dependencies.
3. New-behavior carve-out. Anything in `new_behavior` runs as a normal feature
   red-green cycle (a failing test that demands it, then minimum code).
4. Verify. Run the full `test_command`. Green (== baseline) → success. Red →
   one focused fix attempt; still red → revert the ENTIRE job (tree back to the
   pre-job state) and report failure. Never edit a test assertion to pass a
   refactor — a disagreeing test means the change is wrong.

Output (the caller acts on this without re-reading anything):
`job_id`, `outcome` (`applied` | `failed (reverted)`), `tests_written`
(pins + any new feature tests), `files_touched`, `diffstat`, `suite_status`
(vs baseline), `noticed_not_touched`.

## Worked example

A SOLID rec "extract PricingStrategy protocol; move the three `if kind ==`
branches into Percent/Fixed/Tiered strategy classes; inject the chosen
strategy" arrives as: targets=[pricing.py], change=<that text>,
coverage=covered, baseline_status=green, new_behavior=none.
→ existing suite is the net → apply the extraction → suite green → outcome
`applied`, tests_written=[] (behavior unchanged), files_touched=[pricing.py,
strategies.py].
