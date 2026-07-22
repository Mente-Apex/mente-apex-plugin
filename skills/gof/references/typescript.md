# TypeScript — GoF idioms & test detection

How the 23 patterns translate into *idiomatic* TypeScript. The wrong way to apply
GoF here is to transplant Java: `IFactory` interfaces on everything,
abstract-everything class trees, and `accept()`/`visit()` ceremony where a
discriminated union, a first-class function, or a generator would do. TS's
structural typing, first-class functions, discriminated unions with exhaustive
`switch`, generators, and the built-in `Proxy` make several patterns nearly free
— use the cheap form, and grade an over-engineered implementation down just as
readily as a broken one.

A note on the word "decorator": TS has a language feature called *decorators*
(`@Injectable()` on a class/method). That is **not** the GoF Decorator pattern —
don't conflate them. GoF Decorator in TS is wrapping, usually via a function.

## Per-pattern idioms

### Creational

**Singleton** — an ES module is already a singleton: `export const registry = new
Registry()` evaluated once at first import is almost always the right answer, no
class-static bookkeeping needed. A `static instance` + private constructor is the
textbook form but rarely earns its ceremony in TS. Note the DIP tension recorded
in the `lens-overlap` map: SOLID prefers constructor injection over any singleton,
so weigh both lenses before suggesting one.

**Factory Method** — a `static` alternate constructor (`Shape.fromConfig(cfg)`)
or a plain factory function returning a union type, where the GoF write-up reaches
for a subclass hierarchy. Reserve the subclass-per-product form for when
subclasses genuinely need different *behavior* around creation.

**Abstract Factory** — an `interface` whose methods return a family of related
products, with each concrete factory implementing it. This is the one creational
pattern that earns its interface: family-of-products coupling is what it's for.
Grade down a client that still imports concrete product classes directly.

**Builder** — a fluent chain of methods returning `this`, or — more idiomatic in
TS — a single options object with optional fields and defaults
(`createServer({ port = 8080, tls }: Options)`). Skip a `Director` class unless
the same multi-step sequence is reused across several call sites.

**Prototype** — `structuredClone(value)` for a deep copy of **plain serializable
state** (built into modern runtimes), or object/array spread for a shallow one.
Caveat: `structuredClone` throws `DataCloneError` on functions and does **not**
preserve class prototypes (you get a plain object, losing the instance's type), so
for a class instance use a `clone()` method or a copy constructor instead. A
hand-rolled field-by-field copy is a maintenance trap: new fields silently aren't
cloned — grade C/D and recommend the shape appropriate to the data.

### Structural

**Adapter** — a thin wrapper translating one call signature to another. Often
*nothing at all*: structural typing means two objects with matching method shapes
are already interchangeable without an adapter. Only recommend Adapter when the
signatures genuinely differ.

**Bridge** — composition over inheritance: the abstraction holds a reference to an
implementor object (typed as an interface) rather than subclassing it, avoiding
the `M abstractions × N implementations` subclass explosion.

**Composite** — a shared `interface` (or discriminated union) for leaf and
composite nodes, with the composite delegating to children in a loop or recursion.
Scattered `instanceof` / `"kind" in node` checks through traversal code signal
this pattern is missing.

**Decorator** — a higher-order function wrapping a function
(`const timed = (fn) => (...args) => { ... fn(...args) ... }`), or a class that
holds the wrapped object and forwards the same interface when the decorator needs
state. Prefer the function form until state is actually needed. (Again: not TS
`@decorator` syntax.)

**Facade** — a module exposing 2-3 functions that internally sequence several
subsystem calls. No special mechanism — the win is the client no longer importing
every subsystem.

**Flyweight** — a `Map` cache (or memoization) keyed by the shared-state fields to
intern/reuse instances instead of constructing duplicates. Only worth suggesting
under real memory pressure — don't add a cache for its own sake.

**Proxy** — the built-in `new Proxy(target, handler)` for lazy-loading, access
control, or logging keeps the proxy's surface identical to the subject without
hand-copying methods; a plain wrapper class works too when the surface is small
and known.

### Behavioral

**Chain of Responsibility** — an array of handler functions tried in order, each
returning a sentinel (`undefined`) or throwing to signal "not handled, try the
next" — simpler than a linked list of handler objects with `setNext()`.

**Command** — a function or closure captured and invoked later; add an `undo()`
(pair the function with its inverse in a small object) only when undo is actually
needed, not speculatively.

**Interpreter** — a discriminated-union AST + a recursive function with an
exhaustive `switch` is the idiomatic shape; reach for a parser library once the
grammar grows past a handful of rules rather than hand-rolling a class hierarchy.

**Iterator** — a generator (`*[Symbol.iterator]() { yield ... }` or a `function*`)
beats a hand-written iterator class with manual `next()`/`done` bookkeeping in
almost every case. Write an explicit iterator object only when iteration must be
paused, inspected, or restarted in ways a generator can't express cleanly.

**Mediator** — a coordinator object colleagues call into instead of calling each
other, collapsing many-to-many references into many-to-one. Watch for the mediator
becoming a god object — that's a SRP handoff, not a reason to avoid Mediator.

**Memento** — an immutable snapshot, often `structuredClone` of the relevant state
(plain data — same prototype/function caveat as Prototype above) or a `readonly`
record, returned from `save()` and restored via `restore(snap)`. No formal
`Memento` class needed when a plain frozen object says the same thing.

**Observer** — an array of callbacks
(`private listeners: ((e: Event) => void)[] = []`) with
`subscribe`/`unsubscribe`/`notify`, or the platform `EventTarget` /
Node `EventEmitter` when you want their tooling. The "observer interface" is just a
function signature, not a class hierarchy, unless observers carry real state.

**State** — a discriminated union + exhaustive `switch` on the current state is
often enough; promote to full state objects (each implementing a shared
interface) only when each state owns several methods' worth of distinct behavior.

**Strategy** — a function parameter (`(order: Order) => number`) passed in or
looked up from a `Record<Kind, Handler>`, exactly like the SOLID OCP idiom —
Strategy and OCP's "record of handlers" recommendation are the same fix seen from
two lenses. Build a class-based strategy hierarchy only when strategies carry
their own configuration/state beyond a closure.

**Template Method** — an `abstract class` with a concrete skeleton method calling
`abstract` hook methods, or — often better in TS — a single function taking the
varying steps as injected callbacks, avoiding a subclass just to override one step.

**Visitor** — a discriminated union + a function with an exhaustive `switch`
(`never` check in the default branch) is the idiomatic TS "visitor": the compiler
flags every operation when a variant is added, with none of the
`accept()`/`visit()` double-dispatch ceremony. Reach for classic double dispatch
only when the element hierarchy is genuinely open and operations must live outside
the elements.

## Test suite detection

| Signal | Suite / command |
|--------|-----------------|
| `package.json` → `scripts.test` | `npm test` (or `pnpm test`/`yarn test`/`bun run test` per lockfile — note bare `bun test` runs Bun's own runner, a different suite) — the project's declared truth |
| `vitest.config.*` or vitest in devDependencies | `npx vitest run` |
| `jest.config.*` / `ts-jest` / jest in devDependencies | `npx jest` |
| `playwright.config.*` / `cypress.config.*` | e2e — run after unit suites; note the runtime cost in the report |
| `deno.json` with tasks | `deno task test` / `deno test` |

Prefer the `scripts.test` entry over invoking runners directly — it carries the
project's flags. If it echoes "no test specified", treat as **no suite**.

**Light verification mode** (no suite): `npx tsc --noEmit` (or the project's
`typecheck` script), lint if configured, run the build if one exists, and smoke-
import touched modules.
