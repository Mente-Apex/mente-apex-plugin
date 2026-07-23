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
- `coverage` — `covered` if the suite exercises the targets, else `none`. This is a
  **claim the engine verifies** (step 1), not a promise it trusts — a `covered` label
  on code the suite never actually runs is the classic way a refactor lands with no real
  net under it.
- `new_behavior` — defaults to none: a behavior-preserving refactor has none;
  set it only when `change` explicitly introduces new behavior. Callers applying a
  lens recommendation pass **none** — a rec that needs behavior change is not a
  refactor job and belongs back with the human.

Execution:
1. Safety net — **verify coverage before trusting it.** A `covered` label means
   nothing if the suite doesn't actually run the target lines, and *that* is where a
   refactor silently lands with no net (and no "tests first"). So confirm it cheaply:
   run the tests that name/import the targets and check they exercise the changed code
   (a coverage run over the targets, or at minimum that a target-touching test exists
   and passes). Confirmed `covered` → the existing suite is the net, and a
   behavior-preserving refactor of covered code correctly writes **no** new test first.
   Not actually covered (or `coverage == none`) → drop to **legacy mode**: write
   characterization pins asserting what the code does *today*, to green, **before**
   touching production code. Pins assert the code's **exact** current values, never
   loose bounds — a structural change that reorders operations is exactly what a loose
   pin would miss. If current behavior looks wrong, flag it — never silently "fix" it;
   the oddity may be load-bearing. Record what the net was (covering tests, or pins
   written) as `coverage_proof` for the output.
2. Apply the smallest faithful version of `change`. Behavior-preserving; house
   style; descriptive names; no new dependencies.
   When cleaning up in the refactor step, clean **to the standard**:
   [../../../docs/clean-code-standard.md](../../../docs/clean-code-standard.md)
   (names, small functions, no hidden side effects, good *why*-comments). This is
   what makes every lens's applied refactor come out clean by construction.
3. New-behavior carve-out. Anything in `new_behavior` runs as a normal feature
   red-green cycle (a failing test that demands it, then minimum code).
4. Verify. On a large suite you need not pay for the whole thing on every
   intermediate step: run a **scoped subset** — the tests exercising the changed
   modules (`pytest -k`/path or `--testmon`; vitest by path; add `-n auto` where
   xdist/parallel is available) — for the inner checks (after the Primary, after each
   rider), and the **full `test_command` once as the job's end gate**. The full run is
   non-negotiable and must be green (== baseline) before the job is reported `applied`
   — it is what catches a distant breakage the subset can't see. Red → one focused fix
   attempt; still red → revert the ENTIRE job (tree back to the pre-job state) and
   report failure. Never edit a test assertion to pass a refactor — a disagreeing test
   means the change is wrong. (When the suite is small, just run it whole each time —
   the two-tier split earns its keep only when the full suite is slow.)

Output (the caller acts on this without re-reading anything):
`job_id`, `outcome` (`applied` | `failed (reverted)`), `tests_written`
(pins + any new feature tests), `coverage_proof` (the verified net: the covering
tests, or the pins written red-first — so the caller can prove a safe refactor ran),
`files_touched`, `diffstat`, `suite_status` (vs baseline, from the **full** end-gate
run), `noticed_not_touched`.

## Worked example

A SOLID rec "extract PricingStrategy protocol; move the three `if kind ==`
branches into Percent/Fixed/Tiered strategy classes; inject the chosen
strategy" arrives as: targets=[pricing.py], change=<that text>,
coverage=covered, baseline_status=green, new_behavior=none.
→ existing suite is the net → apply the extraction → suite green → outcome
`applied`, tests_written=[] (behavior unchanged), files_touched=[pricing.py,
strategies.py].

A GoF rec "extract a Strategy for the three `if kind ==` branches in
`legacy_billing.py`; the module has no test coverage" arrives as:
targets=[legacy_billing.py], change=<that text>, coverage=none,
baseline_status=green, new_behavior=none.
→ `coverage == none` triggers legacy mode: write characterization pins that
pin each branch's exact current output to green FIRST, before touching any
production code → apply the extraction → run the full suite (pins + existing
tests) → green → outcome `applied`, tests_written=[test_legacy_billing.py]
(the characterization pins), files_touched=[legacy_billing.py,
billing_strategies.py, test_legacy_billing.py].
