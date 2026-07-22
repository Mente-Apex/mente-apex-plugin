# clean-architecture in TypeScript — tooling & metrics

The headline checks want the real module graph. TypeScript makes the graph easy
to read (explicit `import ... from` everywhere, no runtime import tricks) but the
*boundaries* subtle: `interface`s are erased at compile time and structural typing
means a seam can exist with no `implements` anywhere. Read the graph with a tool
when one is reachable; **degrade gracefully** when not.

## Detect a graph tool (no hard install)

Try, in order, whatever the environment offers — a project-local install first
(`npx dependency-cruiser --version`, `npx madge --version`), then a one-shot
runner (`pnpm dlx`, `yarn dlx`, `bunx`) matching the project's lockfile. Record
which path succeeded. If **none** is reachable, switch to the **degrade path**
below and state "agent-driven (no graph tool)" in the report.

`dependency-cruiser` is the richer tool (it validates rules *and* draws the
graph); `madge` is lighter and great for cycles + a raw dependency map. Prefer
`dependency-cruiser` when both are present.

## `madge` — the import graph, cycles, and Instability

`madge --json src` emits a `module → [dependencies]` map; compute Instability
(the SDP metric) per component (top-level dir under `src/`) from fan-in / fan-out:

```bash
npx madge --json --extensions ts,tsx --ts-config tsconfig.json src > graph.json
```
`--extensions ts,tsx` is required: madge defaults `fileExtensions` to `js`, and
`--ts-config` only governs path *resolution*, not which files are walked — omit it
and a TS-only `src/` scans to a near-empty graph.
```
For each component C (a directory grouping of modules):
  fan_out (efferent) = distinct components C's modules import
  fan_in  (afferent) = distinct components that import C's modules
  instability I = fan_out / (fan_in + fan_out)   # 0 = stable, 1 = unstable
```
Cycles (ADP): `npx madge --circular --extensions ts,tsx --ts-config tsconfig.json src`
lists every import cycle directly. Report each as the chain of modules/components.

## `dependency-cruiser` — the Dependency Rule as contracts

Express the Dependency Rule as **forbidden rules** and run them (and leave them
behind, like the Python lens leaves an `import-linter` contract). Example
`.dependency-cruiser.cjs` the reviewer drafts from the findings:

```js
module.exports = {
  forbidden: [
    // The Dependency Rule is the FULL ordering web → adapters → application → domain.
    // dependency-cruiser has no "layers" type (unlike import-linter), so encode each
    // inward edge as its own forbidden rule — one rule for `domain` alone lets
    // application→web and adapters→web slip through.
    {
      name: "domain-imports-nothing-outer",
      comment: "domain is the core — imports no outer layer",
      severity: "error",
      from: { path: "^src/domain" },
      to:   { path: "^src/(web|adapters|application)" },
    },
    {
      name: "application-below-adapters-and-web",
      severity: "error",
      from: { path: "^src/application" },
      to:   { path: "^src/(web|adapters)" },
    },
    {
      name: "adapters-below-web",
      severity: "error",
      from: { path: "^src/adapters" },
      to:   { path: "^src/web" },
    },
    {
      name: "framework-out-of-core",
      comment: "domain/application must not import frameworks",
      severity: "error",
      from: { path: "^src/(domain|application)" },
      to:   { path: "node_modules/(express|@nestjs|typeorm|@prisma/client|next)" },
    },
    {
      name: "no-cycles",
      severity: "error",
      from: {},
      to: { circular: true },
    },
  ],
  options: {
    tsConfig: { fileName: "tsconfig.json" },
    // REQUIRED: without this, dependency-cruiser only sees runtime imports and
    // silently misses `import type { … }` — exactly the erased type-only imports a
    // TS boundary violation hides behind.
    tsPreCompilationDeps: true,
  },
};
```
Run: `npx depcruise src --config .dependency-cruiser.cjs`. Write the drafted file
to `docs/reports/clean-architecture/.dependency-cruiser.cjs`; **offer** it as a
committed CI tripwire — never commit it silently.

## Abstractness (appendix) — and its TypeScript caveat

`A = abstract types / total types` per component. In TypeScript this is **even
more approximate than in Python**: `interface`s and `abstract class`es are
countable, but interfaces are *erased at compile time* and structural typing
means many seams are implicit (any object of the right shape satisfies a port
with no nominal marker). So `A` — and therefore `D = |A + I − 1|` — undercounts
abstraction wherever the codebase leans on structural typing (which idiomatic TS
does heavily). Emit the Main-Sequence table only under `--metrics`, labelled
approximate, and lean on the Dependency-Rule / Screaming-Architecture findings
instead — those don't depend on the metric.

## Degrade path (no graph tool)

Read imports directly: build a rough module→imports map by scanning
`import ... from "..."` / `import("...")` / `require("...")` statements, resolve
paths via `tsconfig.json` `paths`/`baseUrl`, identify the core/detail split from
folder names and framework imports, and reason about cycles and stability
qualitatively. State the limitation in the report; the Dependency-Rule and
Screaming-Architecture findings survive without a tool — only exact cycle
enumeration and `I`/`A` numbers are weaker.
