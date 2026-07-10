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
runs.

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
    def get(self, order_id: OrderId) -> "Order": ...
    def add(self, order: "Order") -> None: ...
```
`Protocol` is the purest DIP: the domain declares the shape it needs, and the
concrete `SqlAlchemyOrderRepository` *structurally matches* it **without importing
anything from the domain** — the concretion need not know the abstraction exists
at import time. Structural matching also means an in-memory `FakeOrderRepository`
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

    def __eq__(self, other) -> bool:              # identity equality
        return isinstance(other, type(self)) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self._id)
```
The `Specification` base (repository issue #55) is the same story: it needs the
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

## Unit of work

```python
from typing import Protocol

class UnitOfWork(Protocol):
    orders: OrderRepository
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, *exception_details) -> None: ...
    def commit(self) -> None: ...
    def collect_new_events(self) -> list: ...

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
class PlaceOrderService:
    def __init__(self, unit_of_work: UnitOfWork, event_bus):
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

## Testing note

Domain-core tests need no mocks: build real aggregates and value objects, call
methods, assert outcomes and raised events. If a domain test needs a mock, the
boundary is broken — flag it (see `tdd`'s `references/ddd_testing.md`).
