# DDD in TypeScript — concrete idioms

The tactical patterns from `ddd-core.md`, rendered in idiomatic TypeScript. Two
things differ from the Python idioms and drive most of the advice here:
structural typing (a port needs no `implements`; any matching shape satisfies it),
and the absence of free value equality (objects compare by reference, so value
objects must supply their own `equals`). Persistence in TS is almost always
async, so ports return `Promise`s.

## Value objects — immutable, self-validating, with explicit equality

```ts
export class Money {
  private constructor(
    readonly amountCents: number,
    readonly currency: string,
  ) {}

  static of(amountCents: number, currency: string): Money {
    if (amountCents < 0) throw new Error("Money cannot be negative");
    if (currency.length !== 3) throw new Error("currency must be ISO-4217");
    return new Money(amountCents, currency);
  }

  add(other: Money): Money {
    if (this.currency !== other.currency)
      throw new Error("cannot add different currencies");
    return Money.of(this.amountCents + other.amountCents, this.currency);
  }

  equals(other: Money): boolean {
    return this.amountCents === other.amountCents && this.currency === other.currency;
  }
}
```
`readonly` fields + a private constructor behind a validating factory make it
immutable and always-valid; `add` returns a new value. Unlike Python's frozen
dataclass, TS gives **no** structural equality — `a === b` is reference identity,
so a value object that will be compared or used as a set/map key **must** define
`equals` (and callers must use it). A VO missing `equals` is a finding.

## Typed identities — branded types (zero-cost) or a tiny class

The idiomatic, allocation-free identity in TS is a **branded type**:

```ts
export type OrderId = string & { readonly __brand: "OrderId" };
export const OrderId = {
  of: (value: string): OrderId => value as OrderId,
  new: (): OrderId => crypto.randomUUID() as OrderId,   // Node 19+/browser; else `import { randomUUID } from "node:crypto"`
};
```
The brand exists only at compile time, so a raw `string` won't silently pass
where an `OrderId` is required, yet there's no wrapper object at runtime.
Application-generated identity (mint the UUID before persistence) keeps the
aggregate whole in memory and lets domain events carry the id before any adapter
runs. Reach for a small class only when the identity needs behavior of its own.

## Ports are interfaces; domain base classes are abstract classes

Not everything abstract is a *port*. The split is the same as in Python; only the
mechanism changes:

| Kind | What it is | Examples | Use |
|------|------------|----------|-----|
| **Port** | a seam to infrastructure the domain *depends on* | `OrderRepository`, `UnitOfWork`, `EmailSender`, `Clock` | **`interface`** |
| **Domain base class** | shared behavior *inside* the domain | `AggregateRoot`, `Entity`, `DomainEvent`, `Specification` | **`abstract class`** |

### Ports use `interface` (structural — keeps the domain import-clean)

```ts
export interface OrderRepository {
  get(orderId: OrderId): Promise<Order>;
  add(order: Order): Promise<void>;
}
```
Structural typing is the purest DIP here: the concrete `PrismaOrderRepository`
*structurally matches* the interface **without importing anything from the
domain** and without an `implements` clause — though writing `implements
OrderRepository` on the adapter is good practice for a clearer compile error, it
must live in the adapter layer, never pull the port toward infrastructure. The
same structural match means an in-memory `FakeOrderRepository` satisfies the port
for free, which is what lets domain tests run with no mocks. Do **not** reach for
a class + `abstract` method just to declare a port — that adds a runtime artifact
where an erased `interface` says it better.

### Domain base classes use `abstract class`

`AggregateRoot` is **not** a port you inject — it is a base with real behavior
(event recording, identity equality), so it is an `abstract class` by design:

```ts
export abstract class AggregateRoot<TId> {
  private readonly events: DomainEvent[] = [];
  protected constructor(readonly id: TId) {}

  protected record(event: DomainEvent): void {
    this.events.push(event);
  }

  collectEvents(): DomainEvent[] {
    return this.events.splice(0, this.events.length);
  }

  equals(other: AggregateRoot<TId>): boolean {   // identity equality, same concrete type
    return other.constructor === this.constructor && other.id === this.id;
  }
}
```
A `Specification` base is the same story: it needs the `and` / `or` / `not`
combinator *implementations*, so it is an `abstract class`, not an interface. When
a port genuinely needs a little shared code, combine both — an `interface` for the
type seam plus a small concrete helper — rather than fattening the interface.

## Repository adapter (Prisma) — persistence-oriented

```ts
export class PrismaOrderRepository implements OrderRepository {
  readonly seen = new Set<Order>();               // aggregates touched this txn; deduped by reference
  // Type the client as Prisma.TransactionClient (the subset $transaction hands you) —
  // a full PrismaClient is assignable to it, so both the transactional and the
  // standalone construction sites type-check with no cast.
  constructor(private readonly client: Prisma.TransactionClient) {}   // injected; never `new`ed here

  async get(orderId: OrderId): Promise<Order> {
    const row = await this.client.order.findUnique({ where: { id: orderId } });
    if (row === null) throw new OrderNotFound(orderId);
    const order = toDomain(row);                  // returns a whole aggregate
    this.seen.add(order);
    return order;
  }

  async add(order: Order): Promise<void> {
    await this.client.order.create({ data: toRow(order) });
    this.seen.add(order);
  }
}
```
The port lives with the domain/application; this adapter is injected at the
composition root. It returns a fully-constituted `Order`, never a raw row.

## Unit of work

TS ORMs expose transactions as a callback (`prisma.$transaction`,
`dataSource.transaction`). Model the UoW as a port over that so the application
stays framework-free:

```ts
export interface UnitOfWork {
  run<T>(work: (repos: { orders: OrderRepository }) => Promise<T>): Promise<T>;
  collectNewEvents(): DomainEvent[];
}

export class PrismaUnitOfWork implements UnitOfWork {
  private touched: Order[] = [];
  constructor(private readonly client: PrismaClient) {}

  async run<T>(work: (repos: { orders: OrderRepository }) => Promise<T>): Promise<T> {
    return this.client.$transaction(async (tx) => {   // tx is Prisma.TransactionClient
      const orders = new PrismaOrderRepository(tx);
      const result = await work({ orders });
      this.touched = [...orders.seen];
      return result;
    });
  }

  collectNewEvents(): DomainEvent[] {
    return this.touched.flatMap((order) => order.collectEvents());
  }
}
```
Publish events *after* the transaction commits, never mid-transaction (see the
event lifecycle in `ddd-core.md`). If the project has no UoW abstraction and
threads the ORM's transaction callback through services directly, that's a
DIP finding — the framework's transaction API has leaked into the application.

## Application service — orchestrates, holds no business rules

```ts
export class PlaceOrderService {
  constructor(
    private readonly unitOfWork: UnitOfWork,     // both injected — DIP
    private readonly eventBus: EventBus,
  ) {}

  async handle(command: PlaceOrder): Promise<OrderId> {
    const orderId = await this.unitOfWork.run(async ({ orders }) => {
      const order = Order.place(OrderId.new(), command.lines);   // factory
      await orders.add(order);
      return order.id;
    });
    for (const event of this.unitOfWork.collectNewEvents())      // after commit
      this.eventBus.publish(event);
    return orderId;
  }
}
```

## Testing note

Domain-core tests need no mocks: build real aggregates and value objects, call
methods, assert outcomes and recorded events. If a domain test needs `vi.mock`,
the boundary is broken — flag it (see `tdd`'s `references/ddd_testing.md`).
