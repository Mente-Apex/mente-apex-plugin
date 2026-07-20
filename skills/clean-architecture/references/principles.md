# clean-architecture rubric — the component/dependency-graph altitude

Calibration, not a lesson. This altitude is the **component** — a deployable /
package unit — and how components depend on each other. It sits above `solid`
(classes) and orthogonal to `ddd` (domain). Every finding must argue its
reader / change-safety impact.

## The carve (non-overlap)

- `ddd` asks *"is the domain modelled well?"*; this asks *"is the dependency
  structure sound, regardless of domain richness?"*
- `solid` owns the five class-level principles; this is graph topology + their
  component-scale cousins. Cross-reference `../../../docs/lens-overlap.md`; never
  restate a `solid` finding.

## Headline checks (default run) — robust, tool-assisted, actionable

1. **The Dependency Rule / boundaries.** Source dependencies point inward toward
   policy. **Violation:** a domain / use-case / core module imports a web
   framework, ORM, DB driver, or other outer-layer detail — the cardinal finding.
   The framework/DB must be a replaceable **detail** at the edge, reached through
   a port. Mechanically checkable as an `import-linter` forbidden/layers contract.
2. **ADP — no cycles.** The component/import graph must be acyclic. A cycle fuses
   packages into one un-releasable blob; any change forces revalidating the loop.
   Fix by inverting one edge (DIP) or extracting a shared component. Exactly
   detectable on the import graph.
3. **SDP — stability direction.** Depend toward stability. **Instability**
   `I = fan-out / (fan-in + fan-out)` (0 = stable, 1 = unstable). **Violation:** a
   much-depended-on (low-`I`) component importing a volatile (high-`I`) one. Robust
   — computed from import counts only, no "abstractness" needed.

## Secondary checks (opt-in `--cohesion`)

4. **Component cohesion — REP / CCP / CRP.**
   - **REP** — a component should be a coherent, releasable, versioned theme.
     *Smell:* grab-bag `utils`/`common`/`helpers` with unrelated contents.
   - **CCP** (SRP for components) — classes that change together belong together.
     *Evidence:* git co-change of files that live in different packages, or one
     requirement rippling across many.
   - **CRP** (ISP for components) — don't force importers to depend on a fat
     package when each uses only a disjoint slice.
5. **Screaming Architecture.** Top-level layout should reveal use cases
   (`billing/`, `orders/`) not the framework (`controllers/`, `models/`,
   `views/`). One repo-level observation.
6. **Main Component / composition root.** Wiring belongs at the outermost entry
   point. *Smell:* infrastructure constructed **inside** core code (the same smell
   as #1, seen as wiring), or no single composition root at all.

## Appendix (opt-in `--metrics`) — caveated

7. **SAP / the Main Sequence.** **Abstractness** `A = abstract classes / total`.
   Healthy line `A + I = 1`; **distance** `D = |A + I − 1|`; Zone of Pain
   (stable + concrete), Zone of Uselessness (abstract + unstable). **`A` is
   approximate in Python** — duck typing and `Protocol`s defeat "count the
   abstract classes." Present as structural-health context, **never a finding to
   refactor toward**.

## When NOT to flag (judgment, not ceremony)

- **Do NOT** demand boundaries a single-deployable app hasn't earned — partial
  boundaries are legitimate YAGNI.
- **Do NOT** chase Main-Sequence distance on a codebase without real
  multi-component granularity (one deployable with informal packages → noise).
- **Do NOT** flag a cycle *within* one intended release-unit's internal modules —
  the concern is **cross-component** cycles.
- **Do NOT** restate a `solid` DIP finding — cross-reference it via the hub.

## Tier assignment (severity)

- **Critical** — a Dependency-Rule violation welding the core to a framework/DB so
  it can't be tested or swapped; a cycle across core components.
- **Major** — an SDP violation on a central component; infrastructure constructed
  in core; a fat grab-bag component many things depend on.
- **Minor** — Screaming-Architecture naming; small cohesion nits; appendix metrics.
