# TypeScript — test-suite idioms

The rubric ([rubric.md](rubric.md)) is what to look for; this file is what it looks like
in a Vitest (or Jest — the vocabulary is the same) suite. **The standard for how a test
should be written is `tdd`'s**
([../../tdd/references/typescript-vitest.md](../../tdd/references/typescript-vitest.md));
this lens audits those suites rather than inventing a second standard.

## Structure

- **`describe` blocks group by behaviour**, and nest at most two deep. A third level is
  usually a missing test file.
- **Co-located `*.test.ts` or a mirrored `tests/` tree** — either convention is fine, but
  a suite that uses both has no convention.
- **`describe` names complete the sentence the `it` starts.**
  `describe("refund", () => it("is refused after thirty days"))` reads as a spec in the
  failure output.

## Craft

- **`it` names state behaviour, not the method.** `it("returns 400 when the cart is
  empty")`, never `it("works")` or `it("test 2")`.
- **One `expect` family per test.** Ten assertions in one `it` means the first failure
  hides the other nine.
- **`expect(...).toEqual` on values over `toHaveBeenCalledWith` on spies**, wherever a
  value exists. A spy assertion pins the call shape; a value assertion pins the behaviour.
- **`await expect(promise).rejects.toThrow(SpecificError)`** — a bare `.rejects.toThrow()`
  passes on any rejection, including the one from the typo in your setup.
- **`it.each` instead of a `for` loop.** Each case reports separately.
- **No conditionals in tests.** An `if` that skips an assertion is a test that passes by
  not looking.

## Async — the failure mode this language owns

- **A missing `await` is a test that passes before the thing happened.** The commonest
  false-green in a TS suite, and Critical when found.
- **A floating promise inside a test** rejects after the test has finished, and the error
  lands in whichever test is unlucky — a flake that blames the wrong file.
- **Fake timers must be restored.** `vi.useFakeTimers()` without `vi.useRealTimers()` in
  teardown makes every later test in the file time-dependent.

## Mocking

- **`vi.mock` at module scope is hoisted**, so it applies to the whole file whether the
  test wanted it or not — a file-wide fact hiding at the top of one test's setup.
- **Mocking your own modules is the DIP smell**, same as elsewhere: cross-reference
  `solid`/`ddd` via the hub rather than filing it twice.
- **Mocking `fetch`, the clock, the filesystem, the payment SDK is correct** and must not
  be filed.
- **`vi.restoreAllMocks()` in `afterEach`** or spies leak between tests; leakage shows up
  as order-dependence, which makes every other result unreliable.

## Tending

- **`it.skip`/`describe.skip` with no reason** is an obsolete pin; a skip that has
  outlived its ticket is dead weight that reads as coverage.
- **Snapshot tests that nobody reads** are the TS-specific vacuous test: a snapshot
  regenerated whenever it fails asserts nothing at all. A snapshot is a real test only
  where its diff is reviewed.
- **A test importing a module that no longer exists** fails at collection — the same
  clear-cut dead test as elsewhere, with the missing module as its proof.

## Where this bends — what is ordinary here and must not be filed

- **Mocking `fetch`, the clock, the filesystem, a payment SDK** is correct boundary
  mocking, not over-mocking. Flagging every `vi.mock` indiscriminately is the failure
  this lens is most prone to.
- **`beforeEach` setup is not duplication.** A suite that shares four lines of arrange
  across ten tests is readable; hoisting them into a cascade of nested `describe`s to
  save the repetition is how a suite becomes unreadable.
- **Type-level tests (`expectTypeOf`, `@ts-expect-error`) assert nothing at runtime and
  are still real tests.** They pin the API's shape, which is the contract most TS
  consumers actually break.
- **A test file longer than its source is normal** for anything with branching. Length
  is not a smell here; unnamed cases are.
