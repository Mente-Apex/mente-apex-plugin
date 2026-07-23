# TypeScript Adapter — Vitest

Stack-specific mechanics for the core TDD cycle. The cycle itself lives in
SKILL.md; this file covers how to execute it in a TypeScript project whose runner
is Vitest. **Jest is near-identical** — see the compatibility note at the end;
you rarely need a separate adapter for it.

## Discovering conventions

Check, in order:

1. **Runner config** — `vitest.config.ts`/`.js`/`.mts`, or a `test` block in
   `vite.config.ts`; failing that, `package.json` → `scripts.test`. Note
   `include`/`exclude` globs, `environment` (`node` vs `jsdom`), `setupFiles`, and
   any path aliases before running anything.
2. **Layout** — either co-located `*.test.ts` / `*.spec.ts` next to source, or a
   `__tests__/` (or `test/`) directory. Follow whichever the project already uses.
3. **Setup files** — read `setupFiles` (global mocks, matchers like
   `@testing-library/jest-dom`) before writing setup code; the helper you need may
   already exist.
4. **How tests are run** — match the project's package manager and script:
   `npm test`, `pnpm test`, `yarn test`, or `npx vitest run`. Running the wrong
   environment (e.g. `node` when the suite needs `jsdom`) produces misleading
   failures.

Greenfield defaults: co-located `*.test.ts`, `describe`/`it`, `expect`, Vitest's
`node` environment.

During the cycle, run the single new test first, then the full suite:

```bash
npx vitest run path/to/thing.test.ts -t "adds two amounts"   # one test, no watch
npx vitest run                                                # full suite
```
Always use `vitest run` (single pass) in the loop, not bare `vitest` (watch mode).

**Refactor jobs on a large suite — two-tier running.** For the *inner* checks (after
the Primary, after each rider), scope to the changed area rather than the whole suite:
`vitest run path/to/changed.test.ts` for the affected files, or
`vitest related <changed-source-files>` to let Vitest select the tests that import
them (Vitest already runs test files in parallel by default). Then run the **full
suite once as the job's end gate** — it must be green before the job is reported
`applied`, since it is what catches a breakage in a test the subset never imported.
When the suite is fast, just run it whole each time; the split earns its keep only on
a slow one.

## Constructor injection is the test seam

A class that takes its collaborators as constructor parameters gets a one-line
setup; a class that `new`s its own database client needs `vi.mock` — which is the
design smell the REFACTOR checklist tells you to fix, not to paper over.

```ts
import { describe, it, expect, beforeEach } from "vitest";

describe("user repository", () => {
  let userRepository: InMemoryUserRepository;
  beforeEach(() => {
    userRepository = new InMemoryUserRepository();   // injected fake, no mocking
  });

  it("stores and retrieves a user", () => {
    const user = new User("Alice", "alice@example.com");
    userRepository.add(user);
    expect(userRepository.getByEmail("alice@example.com")).toEqual(user);
  });
});
```
`toEqual` is structural (deep) equality — the right default for value comparisons;
`toBe` is reference identity, for when you mean the same instance.

## Expected exceptions

```ts
it("rejects a duplicate email", () => {
  userRepository.add(new User("Alice", "alice@example.com"));
  expect(() => userRepository.add(new User("Bob", "alice@example.com")))
    .toThrow(DuplicateEmailError);
});

it("rejects a duplicate email (async)", async () => {
  await expect(service.register("alice@example.com"))
    .rejects.toThrow(DuplicateEmailError);
});
```
Assert on the error type/class, not a substring of the message, unless the message
itself is the contract. For async code, `await expect(promise).rejects.toThrow` —
forgetting the `await` silently passes.

## Table-driven variations — `it.each`

```ts
it.each(["", "noatsign", "@nodomain", "spaces in@email.com"])(
  "rejects invalid email %j",
  (invalidEmail) => {
    expect(() => new User("Test", invalidEmail)).toThrow(ValidationError);
  },
);
```
Use `it.each` when testing the *same behavior* with different inputs. Distinct
behaviors get distinct tests — cramming them into one `it.each` hides which
specification broke. In the one-test-at-a-time cycle, an `it.each` counts as one
test: introduce it with a single row, make it pass, then add rows one at a time.

## Useful built-ins before reaching for anything else

- `vi.fn()` — a spy/stub function; assert calls with `expect(spy).toHaveBeenCalledWith(...)`.
- `vi.spyOn(object, "method")` — wrap a real method at an *infrastructure boundary*.
  If you're spying on your own domain code, the dependency should be injected
  instead (see `ddd_testing.md` — absolute for domain layers).
- `vi.mock("module", factory)` — module-level replacement, hoisted. A last resort
  for third-party boundaries, not for code you own and could inject.
- `vi.stubEnv("KEY", "value")` / `vi.useFakeTimers()` — environment and clock at
  the boundary; pair with `vi.unstubAllEnvs()` / `vi.useRealTimers()` in teardown.
- `os.tmpdir()` + `fs.mkdtemp` — per-test temp dirs; never write test files into
  the repo.

## Jest compatibility

Vitest mirrors Jest for the core assertion/mocking surface. In a Jest project: the
globals `describe`/`it`/`expect`/`beforeEach` and `it.each` are identical; swap
`vi.fn`/`vi.mock`/`vi.spyOn` → `jest.fn`/`jest.mock`/`jest.spyOn` and
`vi.useFakeTimers` → `jest.useFakeTimers`, and run `npx jest path -t "name"` for a
single test, `npx jest` for the suite. **Env-stubbing does not map**: there is no
`jest.stubEnv` — in Jest, set `process.env.KEY` directly (or `jest.replaceProperty`)
and restore it in teardown. Detect the runner from `package.json` devDependencies /
config files and use whichever is present rather than assuming.
