# Lens overlap map (hub)

Every refactor lens's reviewer reads this. The lenses see the same code from
different altitudes; this hub keeps them cross-referencing instead of issuing
conflicting recs. One hub rather than pairwise maps, so adding a lens is additive.

Uses:
1. **Cross-reference** — every finding names its overlapping principle/pattern.
2. **Hand off** — a rec better expressed in the other lens is marked and the other
   skill recommended.
3. **Dedup on a shared branch** — when both lenses run, the second reads the first's
   `docs/reports/<lens>/` and references existing rec IDs instead of duplicating.

| GoF pattern | Category | Serves (SOLID) | Typical shared smell / handoff note |
|---|---|---|---|
| Abstract Factory | Creational | DIP, OCP | domain constructs concrete infra → SOLID DIP; GoF Abstract Factory for product families |
| Builder | Creational | SRP | telescoping/god constructor → separate construction from representation |
| Factory Method | Creational | OCP, DIP | `if/elif` picking a class to instantiate → subclass-chosen product |
| Prototype | Creational | — (performance) | expensive init + cloning; usually no direct principle overlap |
| Singleton | Creational | ⚠ tension with DIP | a module-level singleton is a DIP smell to SOLID; prefer injection — reconcile before suggesting |
| Adapter | Structural | DIP, ISP | incompatible third-party/legacy interface used across call sites |
| Bridge | Structural | DIP, OCP | combinatorial subclass explosion → split into two hierarchies |
| Composite | Structural | LSP, OCP | `isinstance` checks in recursive tree traversal → uniform treatment |
| Decorator | Structural | OCP, SRP | cross-cutting concern (logging/caching/auth) copy-pasted across classes |
| Facade | Structural | SRP, ISP | client orchestrating 3+ subsystem classes in the same sequence |
| Flyweight | Structural | — (performance) | many identical objects consuming memory; not a readability principle |
| Proxy | Structural | SRP, OCP | lazy-load/access-control logic mixed into the subject |
| Chain of Responsibility | Behavioral | OCP, SRP | `if/elif` handler chain whose order/set changes at runtime |
| Command | Behavioral | SRP, OCP | undo/redo/queue; UI action coupled to business logic |
| Interpreter | Behavioral | OCP, SRP | small grammar/expression evaluator crammed into one function |
| Iterator | Behavioral | ISP, LSP | traversal exposes a collection's internal structure |
| Mediator | Behavioral | SRP, DIP | many-to-many tangled dependencies between components |
| Memento | Behavioral | SRP | undo needs a state snapshot without breaking encapsulation |
| Observer | Behavioral | DIP, OCP, SRP | subject calls concrete observers directly → depend on observer interface |
| State | Behavioral | OCP, SRP, LSP | `if/elif` on a state variable with per-state behavior |
| Strategy | Behavioral | OCP, DIP | `if algo == "x"` selecting among interchangeable algorithms (the canonical overlap) |
| Template Method | Behavioral | OCP | copy-pasted algorithm skeletons differing only in steps |
| Visitor | Behavioral | OCP, SRP | `isinstance` dispatch to add operations across a stable hierarchy |

**Reconciliation rule:** when a smell maps to both a SOLID principle and a GoF
pattern (e.g. a duplicated type-switch = OCP + Strategy), it is **one** change, not
two. Whichever lens is running files the rec; the other lens references that rec ID.
For ⚠ entries (Singleton), the lenses can disagree — surface the tension to the human
rather than auto-recommending.

## clean-architecture ↔ the others

`clean-architecture` audits the component/dependency graph (an altitude above
`solid`'s classes and orthogonal to `ddd`'s domain). Shared smells reconcile as
one change; the running lens files it, the other references the rec ID.

| clean-architecture finding | Overlaps | Reconciliation |
|---|---|---|
| dependency-direction violation (core imports framework/DB) | `ddd` (missing port / DIP), `solid` (DIP) | one change; `ddd` frames it as "missing port on aggregate X", CA as "boundary violation: use-case imports the web framework" — whoever runs files it |
| cycle (ADP) | `solid` (DIP inverts an edge) | CA files the cycle; DIP is the fix mechanism, not a second rec |
| composition-root / infra constructed in core | `gof` (Abstract Factory at the boundary), `clean-code` (separate construction from use) | CA files it; GoF/clean-code are the fix idioms |
| Humble Object at a boundary | `gof` (the pattern) | hand off to `gof` |
| Screaming Architecture (top-level layout is technical, not use-case) | `ddd` (package-by-layer-only) | one change, both Minor. CA owns the repo-level layout call; `ddd` files only the language cut — "these package names are not in the ubiquitous language" — and cites CA's rec ID. If only `ddd` runs, it files the whole thing. |

**Carve with `ddd` (the tightest seam):** `ddd` asks *"is the domain modelled
well?"*; `clean-architecture` asks *"is the dependency structure sound, regardless
of domain richness?"* A codebase can pass one and fail the other.

## test-quality ↔ the others

`test-quality` is the only lens that reads `tests/` as its subject; the other five read
`src/`. Most of its findings are test-only (structure, isolation, stale tests) and dedupe
against nothing. It overlaps in exactly two places, and in both it defers the *fix*
up-ladder while owning the *test-side symptom*.

| test-quality finding | Overlaps | Reconciliation |
|---|---|---|
| over-mocking / must mock your own domain | `solid` (DIP), `ddd` (missing port) | the *fix* is a production seam — `solid`/`ddd` file it; test-quality names the symptom ("this test can only run by mocking `X`") and references that rec. Not a second change. |
| duplicated / redundant test body (line-craft duplication) | `clean-code` (DRY) | **carve, not dedup:** clean-code owns line-level duplication *inside* a test; test-quality owns whether the *test itself* is redundant (a stale twin to delete/merge). Usually distinct findings; if genuinely the same edit, clean-code (line craft) files the extraction and test-quality references it. |

**Carve with `clean-code`:** line craft *in* a test file (a badly-named local, a long
line) is `clean-code`'s; the suite *as a test suite* (structure, mocking strategy,
isolation, stale tests) is `test-quality`'s. A test file can be clean line-by-line and
still be a badly-architected, over-mocked, cruft-laden suite.
