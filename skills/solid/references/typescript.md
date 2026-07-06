# TypeScript — SOLID idioms & test detection

TypeScript's structural typing changes what SOLID looks like: interfaces are
free (no implements needed), unions are first-class, and the compiler can
enforce exhaustiveness. Apply the principles through those tools, not through
Java-shaped class hierarchies.

## Per-principle idioms

**SRP** — split at module level; a "barrel god" (`utils.ts`, `helpers.ts`,
800-line `service.ts`) becomes focused modules with intention-revealing names.
Prefer plain functions + module boundaries over classes unless there's state.

**OCP** — two idiomatic, *different* solutions; pick by shape of change:
1. **Discriminated union + exhaustive switch** — when variants are closed-ish
   and behavior lives with the operation. One switch per operation with a
   `never` exhaustiveness check is NOT a violation: the compiler flags every
   site when a variant is added. Only flag switch chains that are duplicated
   *without* exhaustiveness checking.
2. **Interface + implementations (or a record of handlers)** — when variants
   are open-ended or plugin-like:
   `const handlers: Record<Kind, (order: Order) => number>`.
Converting a well-typed exhaustive union into a class hierarchy is a
downgrade — call that out rather than recommend it.

**LSP** — implementations must honor the interface's documented contract: no
`throw new Error("not supported")` in a concrete member, no narrowing of
accepted inputs, no `null` returns the interface doesn't declare. Scattered
`instanceof` / discriminant re-checks in callers signal broken substitution.

**ISP** — interfaces belong to the *consumer*: declare the narrow shape where
it's used (`interface Clock { now(): Date }`) and let structural typing do the
rest. Use `Pick<T, K>` / small composed interfaces instead of importing a fat
service type to use one method. A function parameter typed as the 20-method
`ApiClient` when it calls `get` once is the violation.

**DIP** — inject via constructor parameters or factory closures, typed as
interfaces; construct concretions in the composition root (entry file, DI
container if the framework has one — NestJS/Angular users should use the
framework's injector, not hand-rolling). Kill `export const db = new Db()`
module singletons that business logic imports directly; export a factory and
wire at the edge. Don't wrap language/runtime built-ins (`Math`, `JSON`,
`fetch` at the boundary is fine to wrap *once* for testability, not per-call).

## Test suite detection

| Signal | Suite / command |
|--------|-----------------|
| `package.json` → `scripts.test` | `npm test` (or `pnpm test` / `yarn test` / `bun test` per lockfile: `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb`) — the project's declared truth |
| `vitest.config.*` or vitest in devDependencies | `npx vitest run` |
| `jest.config.*` or jest in devDependencies | `npx jest` |
| `playwright.config.*` / `cypress.config.*` | e2e — run after unit suites; note the runtime cost in the report |
| `deno.json` with tasks | `deno task test` / `deno test` |

Prefer the `scripts.test` entry over invoking runners directly — it carries the
project's flags. If `scripts.test` echoes "no test specified", treat as **no
suite**.

**Light verification mode** (no suite): `npx tsc --noEmit` (or the project's
`typecheck` script), lint if configured, import/require every touched module
via a smoke script or `node --check` for plain JS, run the build if one exists.
