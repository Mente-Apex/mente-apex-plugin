# DDD in Python — concrete idioms

The tactical patterns from `ddd-core.md`, rendered in idiomatic Python. Other
languages fall back to the core reference.

## Value objects — frozen dataclasses, self-validating

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Money:
    amount_cents: int
    currency: str

    def __post_init__(self):
        if self.amount_cents < 0:
            raise ValueError("Money cannot be negative")
        if len(self.currency) != 3:
            raise ValueError("currency must be an ISO-4217 code")

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("cannot add different currencies")
        return Money(self.amount_cents + other.amount_cents, self.currency)
```
`frozen=True` gives immutability and value equality for free; `__post_init__`
makes it self-validating; `add` is side-effect-free (returns a new value).

## Typed identities

```python
from dataclasses import dataclass
from uuid import UUID, uuid4

@dataclass(frozen=True)
class OrderId:
    value: UUID

    @staticmethod
    def new() -> "OrderId":
        return OrderId(uuid4())
```
Application-generated identity (mint the UUID before persistence) keeps the
aggregate whole in memory and lets domain events carry the id before any adapter
runs. The SQLAlchemy default pulls the other way — an `Integer` primary key with
`autoincrement` leaves `order.id` as `None` until `flush()`, so identity equality
and hashing are undefined for an unsaved aggregate. If the schema must keep a
database-generated surrogate for indexing, still mint the *domain* id in the
application and store it as a unique column; the aggregate then never exists
without an identity. (See "Entity identity" in `ddd-core.md` for the tradeoff.)

## Specification — composable business rules

```python
from abc import ABC, abstractmethod

class Specification(ABC):
    @abstractmethod
    def is_satisfied_by(self, candidate) -> bool: ...

    def __and__(self, other: "Specification") -> "Specification":
        return AndSpecification(self, other)

    def __or__(self, other: "Specification") -> "Specification":
        return OrSpecification(self, other)

    def __invert__(self) -> "Specification":
        return NotSpecification(self)


class AndSpecification(Specification):
    def __init__(self, left: Specification, right: Specification):
        self._left, self._right = left, right

    def is_satisfied_by(self, candidate) -> bool:
        return self._left.is_satisfied_by(candidate) and self._right.is_satisfied_by(candidate)


class OrderOverThreshold(Specification):
    def __init__(self, threshold: Money):
        self.threshold = threshold          # public: the translator below has to read it

    def is_satisfied_by(self, order: "Order") -> bool:
        return order.total().amount_cents >= self.threshold.amount_cents
```
`OrSpecification` / `NotSpecification` follow the same two-line shape. Composition
reads in the ubiquitous language:

```python
eligible_for_free_shipping = OrderOverThreshold(Money(5000, "EUR")) & ~ContainsHazardousGoods()
```
The combinators need real *implementations*, which is why `Specification` is an
ABC (a domain base class) and not a `Protocol` port — the same split as
`AggregateRoot` below.

### The repository-translation seam

The port carries one more method — `matching(specification) -> list[Order]`, shown
in the full `OrderRepository` declaration below — and the **adapter** turns the
specification into SQL. The domain never sees a query:

```python
class SqlAlchemyOrderRepository:                         # the same adapter shown in full below
    _TRANSLATORS = {                                     # the finite set this adapter renders
        OrderOverThreshold: lambda specification: OrderRow.total_cents
        >= specification.threshold.amount_cents,
    }

    def matching(self, specification: Specification) -> list["Order"]:
        translator = self._TRANSLATORS.get(type(specification))
        if translator is None:
            raise UntranslatableSpecification(specification)   # explicit, never a silent full scan
        rows = self._session.scalars(select(OrderRow).where(translator(specification)))
        orders = [_to_domain(row) for row in rows]
        self.seen.update(orders)                         # touched this transaction — the UoW drains their events
        return orders
```
Raising on an untranslatable specification is deliberate: the alternative — load
everything and filter with `is_satisfied_by` in Python — is correct only at small
volumes, so make it a decision the adapter states rather than a performance cliff
it hides.

Note what a `type(...)` lookup cannot do: **a composed specification is a different
type**, so `OrderOverThreshold(...) & ~ContainsHazardousGoods()` hits the
`UntranslatableSpecification` branch. Either keep translation to leaf
specifications and compose in memory, or make the translator recursive — add
`AndSpecification`/`OrSpecification`/`NotSpecification` entries that map to
`and_(…)`, `or_(…)`, `not_(…)` over their translated children. Choose
deliberately; the recursive version is ~10 more lines and is usually worth it.

## Protocol vs ABC — the decision, once

Not everything abstract is a *port*. Split the two families and the choice is
mechanical:

| Kind | What it is | Examples | Use |
|------|------------|----------|-----|
| **Port** | a seam to infrastructure the domain *depends on* | `OrderRepository`, `UnitOfWork`, `EmailSender`, `Clock` | **`typing.Protocol`** |
| **Domain base class** | shared behavior *inside* the domain | `AggregateRoot`, `Entity`, `DomainEvent`, `Specification` | **`abc.ABC` / concrete base** |

**Rule of thumb:** *ports → `Protocol`; domain base classes with shared behavior
→ ABC.*

### Ports use `Protocol` (structural, keeps the domain import-clean)

```python
from typing import Protocol

class OrderRepository(Protocol):
    seen: set["Order"]                       # aggregates touched this transaction; the UoW drains their events
    def get(self, order_id: OrderId) -> "Order": ...
    def add(self, order: "Order") -> None: ...
    def matching(self, specification: Specification) -> list["Order"]: ...
```
`Protocol` is the purest DIP: the domain declares the shape it needs, and the
concrete `SqlAlchemyOrderRepository` *structurally matches* it **without importing
the port itself** — the concretion need not know the abstraction exists at import
time. (It does, correctly, import the domain's `Order` and `OrderId`: adapters
depend *inward*. What DIP forbids is the arrow pointing the other way.)
Structural matching also means an in-memory `FakeOrderRepository`
satisfies the port for free, which is what lets domain tests run with no mocks.
Type checkers (mypy/pyright) verify conformance statically; do **not** lean on
`@runtime_checkable`, which only checks that method *names* exist, not signatures.

Reach for **`abc.ABC` on a port** only in these specific cases: you need
fail-at-construction runtime enforcement (an incomplete impl won't instantiate)
without a type checker in CI; the port ships real *default/template* behavior
subclasses reuse; or you rely on `isinstance` dispatch at runtime. A `Protocol`
carrying implementation is a smell — that is the signal you actually wanted an
ABC.

### Domain base classes use ABC / a concrete base

`AggregateRoot` is **not** a port you inject — it is a base with real behavior
(event recording, identity equality), so it is an ABC/base by design, not a
contradiction of "ports are Protocols":

```python
from abc import ABC

class AggregateRoot(ABC):
    def __init__(self, aggregate_id):
        self._id = aggregate_id
        self._events: list = []

    @property
    def id(self):
        return self._id

    def _record(self, domain_event) -> None:
        self._events.append(domain_event)

    def collect_events(self) -> list:
        recorded_events = self._events[:]
        self._events.clear()
        return recorded_events

    def __eq__(self, other) -> bool:              # identity equality, exact type (symmetric)
        return type(self) is type(other) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self._id)
```
The `Specification` base above is the same story: it needs the
`&` / `|` / `~` combinator *implementations*, so it is an ABC, not a Protocol.

When a port genuinely needs a little shared code, combine both rather than
compromise: a `Protocol` for the type seam plus a small concrete mixin for the
helpers — the exception, not the default.

## Repository adapter (SQLAlchemy) — persistence-oriented

```python
class SqlAlchemyOrderRepository:            # matches the OrderRepository Protocol
    def __init__(self, session):
        self._session = session             # injected; never constructed here
        self.seen: set[Order] = set()       # aggregates touched this transaction

    def get(self, order_id: OrderId) -> Order:
        row = self._session.get(OrderRow, order_id.value)
        if row is None:
            raise OrderNotFound(order_id)
        order = _to_domain(row)             # returns a whole aggregate
        self.seen.add(order)
        return order

    def add(self, order: Order) -> None:
        self._session.add(_to_row(order))
        self.seen.add(order)
```
The port lives with the domain/application; this adapter is injected at the
composition root. It returns a fully-constituted `Order`, never a row.

`add` is an explicit write — that is what makes this **persistence-oriented**.

### …versus collection-oriented, which SQLAlchemy's ORM also supports

With the ORM's identity map and dirty tracking, a mutated aggregate is written on
commit with no `save` call at all:

```python
class CollectionOrientedOrderRepository:    # satisfies the same OrderRepository Protocol
    def __init__(self, session):
        self._session = session
        self.seen: set[Order] = set()

    def get(self, order_id: OrderId) -> Order:
        order = self._session.get(Order, order_id.value)  # a tracked, mapped aggregate
        if order is None:
            raise OrderNotFound(order_id)                 # Session.get returns None, not a raise
        self.seen.add(order)
        return order

    def add(self, order: Order) -> None:
        self._session.add(order)                          # only *new* aggregates are added
        self.seen.add(order)
```
```python
order = unit_of_work.orders.get(order_id)
order.cancel(reason)          # no repository call — the UoW's commit flushes the change
```
`matching` is identical to the persistence-oriented adapter's — the translation
seam is orthogonal to the write style. `seen` is not: both adapters must keep it,
because `collect_new_events` below drains events from exactly that set, and a
repository that skips the bookkeeping silently publishes nothing.

This is the more literal reading of "collection-like", and it is cheaper to use
correctly. Its price: it requires **imperative mapping** (`registry.map_imperatively`)
so the domain class stays free of SQLAlchemy imports — declarative `Base`
subclasses put the ORM inside the domain and cost you the DIP. It also only works
while aggregates are *mutated* rather than rebuilt, and a detached instance
silently stops tracking.

Pick one style per codebase. Mixing them — some aggregates persisting implicitly,
some needing `add`/`save` — is where "my change didn't stick" bugs come from.

## Unit of work

```python
from collections.abc import Iterator
from typing import Protocol

class UnitOfWork(Protocol):
    orders: OrderRepository
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, *exception_details) -> None: ...
    def commit(self) -> None: ...
    def collect_new_events(self) -> Iterator[DomainEvent]: ...   # a generator; annotate as what it yields

class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def __enter__(self):
        self._session = self._session_factory()
        self.orders = SqlAlchemyOrderRepository(self._session)
        return self

    def __exit__(self, *exception_details):
        self._session.rollback()
        self._session.close()

    def commit(self):
        self._session.commit()

    def collect_new_events(self):
        for order in self.orders.seen:          # aggregates touched this UoW
            yield from order.collect_events()
```
`collect_new_events` drains the events recorded on every aggregate the
repositories handed out or accepted this transaction — the application service
publishes them *after* `commit`, never mid-transaction (see the event lifecycle
in `ddd-core.md`).

## Application service — orchestrates, holds no business rules

```python
from typing import Protocol

class EventBus(Protocol):                    # the other injected port — typed, like the UoW
    def publish(self, domain_event: DomainEvent) -> None: ...

class PlaceOrderService:
    def __init__(self, unit_of_work: UnitOfWork, event_bus: EventBus):
        self._unit_of_work = unit_of_work   # both injected — DIP
        self._event_bus = event_bus

    def handle(self, command: "PlaceOrder") -> OrderId:
        with self._unit_of_work as unit_of_work:
            order = Order.place(OrderId.new(), command.lines)   # factory
            unit_of_work.orders.add(order)
            unit_of_work.commit()
            for domain_event in unit_of_work.collect_new_events():
                self._event_bus.publish(domain_event)           # after commit
        return order.id
```

## Supple design — side-effect-free functions and stated invariants

`Money.add` above is the pattern: a query on a frozen value object that computes
and returns, mutating nothing. Keep the mutating commands on the aggregate root
and make the invariant they protect a *stated* assertion, not an inferred one:

```python
from functools import reduce

class Order(AggregateRoot):
    MAX_LINES = 50

    def total(self) -> Money:                      # side-effect-free query
        zero = Money(0, self._currency)            # an empty order totals zero, it does not raise
        return reduce(Money.add, (line.subtotal() for line in self._lines), zero)

    def add_line(self, line: OrderLine) -> None:   # command — mutates, returns nothing
        self._check_invariants(pending_line=line)
        self._lines.append(line)
        self._record(LineAdded(self.id, line.sku))

    def _check_invariants(self, pending_line: OrderLine | None = None) -> None:
        prospective_line_count = len(self._lines) + (0 if pending_line is None else 1)
        if prospective_line_count > self.MAX_LINES:
            raise TooManyOrderLines(self.id, prospective_line_count)
        if self._status is OrderStatus.PLACED:
            raise OrderAlreadyPlaced(self.id)
```
Three habits in one shape: `total` computes without mutating; `add_line` mutates
without returning a computed result; `_check_invariants` names the aggregate's
invariant in one place, so the rule gated at the modeling gate is findable in the
code. Do **not** use bare `assert` for invariants — `python -O` strips it.

## Testing note

Domain-core tests need no mocks: build real aggregates and value objects, call
methods, assert outcomes and raised events. If a domain test needs a mock, the
boundary is broken — flag it (see `tdd`'s `references/ddd_testing.md`).
