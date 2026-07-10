# DDD tactical core — the always-loaded rubric

You know these patterns; this file is calibration, not a lesson. It states what
this skill treats as canonical, and — as important — the **when-NOT-to** rules
that keep a simple domain from drowning in ceremony. Both `analyze` agents and
the `design` orchestrator read it, so they judge against one yardstick.

## The four layers and the one rule

`domain → application → adapters → web`. **Dependencies point inward only.**
- **Domain** imports nothing from the outer layers. Pure business logic.
- **Application** imports domain + port abstractions only. Orchestrates use
  cases; owns the transaction boundary; holds no business rules.
- **Adapters** depend inward on ports (repository/UoW impls, API clients).
- **Web/HTTP** is the composition root, built last, and only if needed — it wires
  concrete adapters and injects them inward.

DIP restated: high-level policy (domain, application) depends only on
abstractions (ports); concretions are injected at the composition root; nothing
in the domain constructs a database client, HTTP session, or clock.

## Entities vs value objects

- **Value object** — defined by its attributes, not an identity. Immutable,
  self-validating, side-effect-free, equal by value (`Money`, `Email`,
  `DateRange`). Prefer these; they carry behavior and make tests trivial.
- **Entities** — defined by an identity that persists through every state change.
  Model the identity as a typed value object (`OrderId`), never a bare `str`.

## Aggregates — consistency boundaries (and their four rules)

An **aggregate** is a cluster of objects treated as one unit for data changes;
its **root** is the only member outside code may hold a reference to, and it
guards an **invariant** — the rule that must always hold. The four design rules:
1. **Keep aggregates small** — ideally the root plus the values it needs to
   enforce its invariant.
2. **Reference other aggregates by identity (ID), never by object reference.**
3. **Modify one aggregate per transaction.**
4. **Consistency across aggregates is eventual**, reached via domain events —
   not by editing two aggregates in one transaction.

## Factories

Creating a complex aggregate so it is never born invalid is a **domain**
responsibility. Put that logic in a factory (a classmethod, a standalone
function, or a factory object) rather than scattering construction across
services. (This is core tactical DDD, not merely a `/gof` suggestion.)

## Domain events — the full lifecycle

Not just a noun:
1. **Raised** — a behavior method on the aggregate records an event
   (`self._events.append(OrderPlaced(...))`) as part of enforcing its invariant.
2. **Dispatched** — after the **unit of work commits**, the recorded events are
   published to handlers. Never dispatch mid-transaction.
3. **Handled** — handlers react, typically by acting on *another* aggregate.
   This is the mechanism for the eventual consistency in aggregate rule 4.

### Domain event vs integration event
- **Domain event** — stays *inside* the bounded context; its shape can change
  freely with the model.
- **Integration event** — the *published, versioned* contract emitted *between*
  bounded contexts. Route these through the ACL / published-language boundary
  (see `strategic.md`). Do not leak internal domain events across a context edge.

## Domain service vs application service

Conflating these causes the anemic-domain and fat-service smells:
- **Domain service** — genuine business logic that belongs to no single entity or
  value object (e.g. a funds transfer touching two accounts). Lives in the domain
  layer; stateless; expressed in the ubiquitous language.
- **Application service** — orchestrates one use case: load aggregate(s) via
  repositories, call domain methods, commit the unit of work, dispatch events. It
  is the transaction/security boundary and holds **no business rules**.

## Ports, repositories, unit of work

- **Port** — an abstraction (Protocol/ABC) the domain/application depends on; the
  seam where an adapter is injected. Keep ports small and client-specific (ISP).
- **Repository** — a collection-like abstraction over one aggregate root's
  persistence. Returns **fully-constituted aggregates**; hides the query
  mechanism; one per aggregate root (not one per table, not a generic god-repo).
- **Unit of work** — the transactional boundary for a single change: begin →
  do work → commit/rollback, then dispatch the domain events raised during it.
  Owned by the application service.

## When NOT to (judgment, not ceremony)

- **Do NOT** make a value object where a bare primitive is genuinely fine and
  carries no rule.
- **Do NOT** add a unit of work when a single repository call is the entire
  transaction.
- **Do NOT** create a repository for a non-root entity — access it through its
  aggregate root.
- **Do NOT** split one cohesive bounded context into ceremony, or model an
  aggregate whose "invariant" is nothing more than "these fields exist".
- **Do NOT** introduce domain events for a change that never crosses an aggregate
  boundary and has no subscriber.
