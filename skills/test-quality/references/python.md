# Python — test-suite idioms

The rubric ([rubric.md](rubric.md)) is what to look for; this file is what it looks like
in a pytest suite. **The standard for how a test should be written is `tdd`'s**
([../../tdd/references/python-pytest.md](../../tdd/references/python-pytest.md)) — this
lens audits the suites that skill writes, so it cites that standard rather than inventing
a second one. What is below is the *audit* view: what the smells look like here, and what
is normal Python testing that should not be filed.

## Structure

- **Test modules mirror the source tree**, `tests/test_<module>.py`. A flat `tests/`
  directory over a packaged source tree is a structure finding — a reader cannot answer
  "where are this module's tests" without grepping.
- **Classes group by behaviour, not by method under test.** `class TestWhenTheCardIsExpired`
  reads as a spec; `class TestChargeCard` with fifteen unrelated methods is a pile with a
  lid.
- **`conftest.py` at the widest scope a fixture is used.** A fixture at the root used by
  one module is at the wrong level, and the root conftest is the one file everyone loads.

## Craft

- **Name as spec.** `test_refund_is_refused_after_thirty_days`, not `test_refund_2`.
  A test whose name does not say the behaviour makes a failure report useless.
- **Arrange-Act-Assert, with the act one line.** If you cannot see which line is the act,
  the test is testing more than one thing.
- **`assert` on the value, not on the mock**, wherever a value is available.
  `mock.assert_called_once_with(...)` pins the implementation's call shape; asserting the
  outcome pins the behaviour.
- **`pytest.raises` needs `match=`.** Without it the test passes on a different
  `ValueError` raised for a different reason three frames earlier.
- **No logic in tests.** An `if` in a test means two tests; a `for` over cases means
  `@pytest.mark.parametrize`, which reports each case separately instead of stopping at
  the first failure.
- **`parametrize` ids where the case is not obvious** — `ids=["expired", "cancelled"]`
  turns `test[case2]` into a readable failure line.

## Fixtures

- **A fixture that returns a Mock of your own domain class is the over-mocking smell**,
  not a fixture. See "Strategy" below.
- **`yield` fixtures for anything with teardown**; a fixture that opens a resource and
  never closes it leaks across the session.
- **Factory fixtures over frozen objects** when tests need variants:
  `def make_order(**overrides)` beats `order_with_two_lines`, `order_expired`,
  `order_refunded` — three fixtures that drift apart.
- **`autouse=True` is invisible action at a distance.** Legitimate for isolation
  (clearing an env var, a temp cwd); a smell for anything that changes what a test means.

## Strategy

- **Mocking your own domain classes is a DIP finding, not a test finding.** If a service
  test must patch three collaborators, the production design is missing ports —
  cross-reference `solid`/`ddd` via the hub and file the test-side symptom only.
- **Mocking at the boundary is correct and must not be filed**: the payment gateway, the
  clock, the mailer, the filesystem. Restraint here is the judgement this lens is for.
- **`monkeypatch` over `unittest.mock.patch` for env and attributes** — it undoes itself,
  and a `patch` that outlives its test is a cross-test coupling bug that surfaces as
  order-dependence.
- **Order-dependence is a defect.** If `pytest -p no:randomly` passes and a shuffled run
  fails, tests are sharing state; that is Critical, because every other result in the
  suite is now unreliable.

## Tending

- **A test importing a symbol the source no longer defines is dead** — its proof is the
  collection error, which is the one deletion admissible without a coverage tool. Confirm
  the symbol is *gone*, not moved.
- **Vacuous tests**: a test whose only assertion is on a mock it configured itself proves
  the mock works. The mutation gate is what finds these mechanically.
- **Obsolete pins**: `@pytest.mark.skip` with no reason, or `xfail` that now passes
  (`strict=True` turns that into a failure instead of a silent pass).
