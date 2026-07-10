# SOLID ↔ GoF overlap map

Both reviewers read this. The two lenses see the same code from different angles;
this map keeps them cross-referencing instead of issuing conflicting recs.

Uses:
1. **Cross-reference** — every finding names its overlapping principle/pattern.
2. **Hand off** — a rec better expressed in the other lens is marked and the other
   skill recommended.
3. **Dedup on a shared branch** — when both lenses run, the second reads the first's
   `*-reports/` and references existing rec IDs instead of duplicating.

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
