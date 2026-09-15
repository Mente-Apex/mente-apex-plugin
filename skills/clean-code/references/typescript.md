# TypeScript — clean-code idioms

The standard ([docs/clean-code-standard.md](../../../docs/clean-code-standard.md)) is
the rubric; this file is what its principles look like in TypeScript, and where applying
them literally makes TypeScript worse.

## Naming and types

- **`I`-prefixed interfaces are a C# habit.** `interface IUserService` — the `I` says
  nothing the keyword has not already said.
- **A type alias is a name.** `type Milliseconds = number` turns an unreadable `number`
  parameter into a documented one at zero runtime cost. Primitive-obsessed signatures
  (`(id: string, name: string, email: string)`) are a naming finding here, not just a
  design one — they are trivially transposable at the call site.
- **`any` is an unchecked assertion.** Each one is a place the compiler was told to stop
  helping. `unknown` plus a narrowing check is the honest form; file `any` in new code as
  Major, and `any` at a boundary that parses external input as Critical.
- **Non-null `!` is the same bargain.** It says "trust me" where a check would say why.

## Functions

- **Options object past three parameters**, for the same reason Python takes
  keyword-only: `createReport(path, true, false, null)` cannot be read.
- **Discriminated unions over boolean flags.** Two booleans encode four states, of which
  typically two are meaningless; a union names only the states that exist and the
  compiler checks exhaustiveness.
- **`async` functions that never await are lying** about their cost; a function typed
  `Promise<T>` makes every caller `await`, which is contagious.
- **Return early; avoid the ternary ladder.** A nested ternary is a conditional written
  to fit on one line at the reader's expense.

## Modules and classes

- **Prefer a module of functions to a class with no state.** A class whose methods never
  touch `this` is a namespace with extra ceremony.
- **`readonly` on anything not reassigned**, and `as const` for literal tables. Both are
  free, and both tell the reader what cannot move.
- **Barrel files (`index.ts` re-exports) are a cycle factory.** Convenient at the call
  site, and the shortest path to an import cycle `clean-architecture` will then file.

## Errors

- **`catch (error: unknown)`, then narrow.** TypeScript types a caught value as `unknown`
  for a reason; `error.message` without a check is the same unchecked assertion as `any`.
- **Never `catch {}`.** The TS/JS spelling of `except: pass`.
- **A rejected promise nobody awaits is a silent failure.** A floating promise — a call
  to an `async` function with no `await`, no `.catch`, no `void` — is Critical: the
  failure vanishes and the process keeps going.
- **Throw `Error` subclasses, not strings.** A thrown string has no stack.

## Comments

- **JSDoc that restates the signature is noise** now that the types carry it. Keep JSDoc
  for *why*, for units, and for the surprising edge.
- **`// eslint-disable-next-line` with no reason is a comment that says "I gave up".**
  The rule name plus a reason, or delete the suppression.

## Where this bends

- **`any` in a test fixture or a deliberate boundary shim** is often correct. Judge by
  whether it is *contained*.
- **Small duplication beats a shared generic nobody can read.** A three-level conditional
  type with two call sites is worse than the two concrete types it replaced.
- **`enum` vs union is a project style call**, not a finding. Don't relitigate it file by
  file.
