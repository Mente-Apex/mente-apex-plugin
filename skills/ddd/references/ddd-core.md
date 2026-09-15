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
  Model the identity as a typed value object (`OrderId`) rather than a bare `str`
  wherever more than one identity type exists — see "Entity identity" below.

## Entity identity — three decisions, settled at the modeling gate

Identity is not a database concern that can be deferred; it shapes the ports.

- **Natural vs surrogate.** A natural key is a real-world identifier the business
  already uses (ISBN, IBAN, VAT number); a surrogate is one you mint. Prefer a
  natural key only when the business genuinely treats it as immutable — most
  "natural" keys turn out to be re-issued, corrected, or absent at creation time.
- **Application-generated vs database-generated.** *Application-generated* (mint a
  UUID before persisting) is the default here: the aggregate is whole in memory,
  domain events can carry the id before any adapter runs, and the repository port
  needs no round-trip to hand back an identity. *Database-generated* (auto-
  increment, `@GeneratedValue`) means identity only exists after an INSERT — which
  makes an unsaved aggregate's id `null`, breaks identity equality and hashing,
  and forces event payloads to wait on the transaction. Choose it deliberately,
  not by ORM default.
- **Typed, not primitive.** `OrderId` is a value object, so an `OrderId` cannot be
  passed where a `CustomerId` is expected. A bare `str`/`UUID`/`long` identity is
  a finding whenever more than one identity type exists in the same code.

The choice reaches the ports: application-generated identity is what lets a
repository port be `add(order)` rather than `add(order) -> OrderId`.

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

## Specification — a business rule as a first-class object

A **Specification** gives a business predicate a name in the ubiquitous language
and a home that is neither the entity nor an application service. Its one
operation answers `is_satisfied_by(candidate) -> bool`, and it serves three uses:
**validation** (is this object in a valid state?), **selection** (which objects in
a collection or repository match?), and **construction**-to-order (what must a new
object look like?).

Specifications compose; predicate functions don't. `and` / `or` / `not`
combinators build `EligibleForFreeShipping = OrderOverThreshold(...) &
~ContainsHazardousGoods()`. That is open/closed — a new rule is a new
specification, never an edit to an already-tested one.

**The translation seam is the point.** For selection, the repository *port*
accepts a specification; the concrete adapter **translates** it into SQL, a query
builder, or an index lookup. The domain states the rule; only the adapter knows
the query mechanism. Without that seam, complex rules leak outward as ORM
predicates and the inward-only dependency rule quietly breaks. A translating
adapter necessarily knows the finite set of specifications it can render — keep
that set small, and fall back to in-memory filtering (loading candidates, then
applying `is_satisfied_by`) only where the volume genuinely permits it.

## Domain events — the full lifecycle

Not just a noun:
1. **Raised** — a behavior method on the aggregate records an event
   (`self._events.append(OrderPlaced(...))`) as part of enforcing its invariant.
2. **Dispatched** — after the **unit of work commits**, the recorded events are
   published to handlers. Never dispatch mid-transaction. (One deliberate
   exception exists: a synchronous read-model projection updated inside the same
   transaction, which trades the rule for strong read-your-writes — priced in
   `cqrs.md`, and only on that opt-in.)
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

### Repository semantics — two styles, not interchangeable

The three rules above are not negotiable (whole aggregates out; no `Session`,
query builder, `QuerySet`, or SQL across the port — complex criteria enter as
**Specifications**, which the adapter translates; one repository per aggregate
root). *How* the write happens is where there is a real choice:

| | Collection-oriented | Persistence-oriented |
|---|---|---|
| Mental model | an in-memory set you mutate | explicit `save(aggregate)` calls |
| Writes | implicit — the UoW's **change tracking** / identity map diffs the aggregate at commit | explicit — the service says when |
| Needs | an ORM with dirty tracking (Hibernate/JPA, SQLAlchemy ORM) | nothing; works over a document store, SQL Core, HTTP |
| Fails when | change tracking is absent or the aggregate is rebuilt rather than mutated | a caller forgets to `save` after mutating |

Collection-oriented leans on the unit of work to notice the change;
persistence-oriented makes the write a visible line of code. Either way the
transaction boundary is the unit of work, owned by the application service.
Pick one per codebase and hold to it — a suite where half the repositories
persist implicitly and half need `save()` produces the "my change vanished" bug
class, and it is a legitimate Major finding.

## Modules — packaging in the ubiquitous language

Package names belong to the ubiquitous language. Two layouts:

- **Layer-first** (`domain/ application/ adapters/ web/`) — fine for a *single*
  bounded context, where the layering is the only axis that matters.
- **Concept-first** (`billing/{domain,application,adapters}`, `catalog/{…}`) — the
  right default once there is more than one context or the domain is large. The
  top level then reads as the business, not as a framework tutorial.

Whichever you pick, the inward-only dependency rule still holds **inside** each
module — concept-first moves the layers down a level, it does not dissolve them.

The failure to look for: **package-by-layer-only in a multi-context domain**, so
one concept is smeared across every technical folder and no directory name says
what the system does. That is a Minor structural finding (it obscures the model)
unless it is also hiding a boundary violation, in which case tier it on that.

## Supple Design (high-leverage subset)

Three habits, each with the heuristic that makes it checkable. Aim `tdd`'s
refactor step at these:

- **Intention-revealing interfaces** — name for *what* and *why*, in the
  ubiquitous language. If a caller must read the body to know whether to call it,
  the name has failed.
- **Side-effect-free functions** — compute-and-return belongs on value objects;
  isolate the few commands that mutate onto the aggregate root. A method that both
  mutates *and* returns a computed result is two methods. (Returning the *event*
  a command recorded is not a computed result — `order.place() -> OrderPlaced` is
  fine.)
- **Assertions** — every aggregate invariant named at the modeling gate should be
  findable as an assertion somewhere: a guard clause, constructor validation, or a
  test.

Together these are what make domain-core tests trivial and mock-free — the same
contract `tdd`'s `references/ddd_testing.md` already encodes.

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
- **Do NOT** wrap a one-line predicate used in exactly one place in a
  Specification — it earns its keep through reuse, composition, or the
  repository-translation seam, not through ceremony.
- **Do NOT** reorganize a healthy single-context codebase into concept-first
  modules for its own sake; layer-first is correct there.
- **Do NOT** mint a surrogate identity where the business already has a genuinely
  immutable natural one, and do not model an identity as a value object type per
  aggregate in a domain that has exactly one aggregate.
- **Do NOT** turn Supple Design into a tic: not every mutate-and-return is two
  methods (`list.pop()` is fine), and an assertion restating what the type system
  already guarantees is noise. The three habits are aims for the refactor step,
  not a checklist to satisfy.
- **Do NOT** reach for CQRS, event sourcing, or a saga by default — they are
  opt-in disciplines with real costs. Do not open `cqrs.md`, `event-sourcing.md`,
  or `sagas.md` unless a trigger for that discipline has actually fired: reading
  them as background is how a skill starts finding reasons to recommend them.
  Once one *has* fired, read the file — you cannot price what you have not read.
