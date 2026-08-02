# DDD in Java — concrete idioms

The tactical patterns from `ddd-core.md`, rendered in idiomatic Java (21+, this project
targets 25). Other languages fall back to the core reference.

Java's DDD story is dominated by one thing the other language references do not have to
deal with: **JPA actively fights the tactical patterns.** Read the "anemic model trap"
section before writing any finding about a Spring project — most of what looks like a
lazy developer is actually the ORM's requirements leaking into the domain, and the fix
is different for each cause.

## Value objects — records, self-validating

```java
public record Money(long amountCents, Currency currency) {

    public Money {                                   // compact constructor: validation
        if (amountCents < 0) {
            throw new IllegalArgumentException("Money cannot be negative");
        }
        Objects.requireNonNull(currency, "currency is required");
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("cannot add different currencies");
        }
        return new Money(amountCents + other.amountCents, currency);
    }
}
```

A `record` is the whole value-object pattern in one keyword: immutable, final, with
value equality, `hashCode` and `toString` generated. The compact constructor is the
self-validation seam and runs before the fields are assigned, so there is no window in
which an invalid instance exists. `add` returns a new value rather than mutating.

This is a case where Java is *better served than Python* — `@dataclass(frozen=True)`
still permits `object.__setattr__`; a record's fields are genuinely final.

## Typed identities

```java
public record OrderId(UUID value) {

    public OrderId {
        Objects.requireNonNull(value);
    }

    public static OrderId newId() {
        return new OrderId(UUID.randomUUID());
    }
}
```

Application-generated identity — mint the UUID before persistence — keeps the aggregate
whole in memory and lets domain events carry the id before any adapter runs. It also
avoids the `@GeneratedValue` round-trip that makes an unsaved entity's identity `null`,
which is where most `equals`/`hashCode` bugs in JPA entities come from.

## Interface vs abstract class — the decision, once

Java has no structural typing, so every port is a nominal `interface` the adapter
explicitly `implements`. The decision that matters is the same one Python makes between
`Protocol` and `ABC`:

| Kind | What it is | Examples | Use |
|------|------------|----------|-----|
| **Port** | a seam to infrastructure the domain *depends on* | `OrderRepository`, `EmailSender`, `Clock`, `PaymentGateway` | **`interface`**, declared in the domain package |
| **Domain base** | shared behavior *inside* the domain | `AggregateRoot`, `DomainEvent`, `Specification` | **`abstract class`**, or a sealed interface |

**Where the port interface lives is the entire DIP question.** Declared in the domain
package and implemented by the adapter, the compile-time arrow points inward: the
adapter imports the domain, never the reverse. Declared in the adapter package, or
inherited from Spring Data, the arrow reverses and the Dependency Rule is broken —
regardless of how the runtime wiring looks.

An interface carrying `default` method bodies is the signal you actually wanted an
abstract class, exactly as a `Protocol` carrying implementation is in Python.

## The anemic-model trap — JPA's requirements versus the domain

This is the single most common finding in a Spring codebase, and reporting it as
"the developer wrote getters and setters" misses the cause. `@Entity` **requires**:

- a public or protected **no-arg constructor** — so the object can exist in a state the
  invariants forbid, and the compact-constructor validation above has no equivalent;
- a **non-final class and non-final fields** — so it can be subclassed by a lazy proxy;
- **records are not permitted as entities at all** — they are final and have no no-arg
  constructor. (Hibernate 6 supports records as `@Embeddable` via a custom
  `@EmbeddableInstantiator`, and as query projections — not as `@Entity`.)

So annotating an aggregate `@Entity` forces you to surrender immutability, construction
invariants, and the value-object idiom in the same stroke. Lazy loading compounds it:
the "aggregate" is a proxy that only functions inside an open session, so it is not
whole in memory and a method on it can throw `LazyInitializationException` in
production and never in a test.

Three resolutions, in order of how often they are right:

1. **Use Spring Data JDBC instead of JPA.** It is designed around aggregates: it loads
   and stores a whole aggregate, has no lazy loading, no dirty tracking and no session,
   works with immutable types and constructor binding, and models cross-aggregate
   references as `AggregateReference` rather than an object graph. Where the team is
   still choosing, this is the recommendation — most of this section's problem simply
   does not arise.
2. **Separate the persistence model.** Domain `Order` (record-shaped, validating) plus
   an `OrderEntity` in the adapter plus a mapper. Purest, and the most code; correct
   when the domain is rich enough to pay for it.
3. **Annotate the domain and discipline it.** Package-private no-arg constructor,
   fields private with no setters, behavior-named methods only, `@Embeddable` for value
   objects. Pragmatic, and honest as long as the report says what was traded away.

Report the trade-off, not just the smell. "This aggregate is anemic" is a weaker
finding than "these invariants cannot be enforced because `@Entity` requires a no-arg
constructor; here are the three ways out and what each costs."

## Repositories — the `JpaRepository`-as-port mistake

```java
// ✗ Not a port. Twenty inherited methods, and the domain now imports Spring Data.
public interface OrderRepository extends JpaRepository<Order, Long> { }
```

Extending `JpaRepository` in the domain fails DIP and ISP at once: the domain package
imports `org.springframework.data`, and every caller gains `deleteAll`,
`saveAndFlush`, `findAll(Pageable)` and the rest — persistence operations the domain
never asked for and cannot forbid.

```java
// ✓ The port — declared in the domain, sized to what the domain calls.
public interface OrderRepository {
    Optional<Order> findById(OrderId orderId);
    void save(Order order);
}

// ✓ The adapter — in the persistence package, wrapping Spring Data.
@Repository
class JdbcOrderRepository implements OrderRepository {

    private final SpringDataOrderRepository orders;    // the framework interface, package-private

    JdbcOrderRepository(SpringDataOrderRepository orders) {
        this.orders = orders;
    }

    @Override
    public Optional<Order> findById(OrderId orderId) {
        return orders.findById(orderId.value()).map(OrderRecord::toDomain);
    }
}
```

The adapter returns a fully-constituted `Order`, never a row or an entity. Keep
`SpringDataOrderRepository` package-private so nothing outside the adapter can reach it.

## Transactions are the unit of work

Java's unit of work is `@Transactional`, and it belongs on the **application service** —
not on the aggregate, which must not know that persistence exists, and not on the
repository, where each call would commit independently and the aggregate boundary would
stop meaning anything.

Domain events publish **after commit**, which Spring expresses directly:

```java
@Component
class OrderPlacedHandler {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPlaced event) { … }
}
```

Spring Data's `AbstractAggregateRoot` automates the recording half: call
`registerEvent(...)` inside the aggregate and the events are published when the
repository saves it (`@DomainEvents` / `@AfterDomainEventPublication`). Convenient, at
the cost of a domain base class that extends a Spring type — a Dependency-Rule
violation the team may or may not accept. Flag it as a trade-off, not an error.

## Application service — orchestrates, holds no business rules

```java
@Service
public class PlaceOrderService {

    private final OrderRepository orders;              // ports, injected via constructor
    private final EventPublisher events;

    public PlaceOrderService(OrderRepository orders, EventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public OrderId handle(PlaceOrder command) {
        var order = Order.place(OrderId.newId(), command.lines());   // factory on the aggregate
        orders.save(order);
        return order.id();
    }
}
```

Business rules live in `Order.place`. If this method grows an `if` about pricing or
eligibility, that rule has escaped the domain — the defining symptom of the anemic
model, and the finding to write.

## Sealed interfaces for domain unions

```java
public sealed interface PaymentOutcome {
    record Settled(TransactionId id, Money amount) implements PaymentOutcome { }
    record Declined(DeclineReason reason)          implements PaymentOutcome { }
    record Pending(Instant retryAfter)             implements PaymentOutcome { }
}
```

A closed set of domain states, exhaustively checked: a `switch` over it needs no
`default`, and adding a fourth outcome produces a compile error at every site that must
now handle it. This replaces both the "status enum plus nullable fields" shape and the
Visitor pattern, and it is the strongest reason to be on a modern JDK for domain work.

## Bounded contexts have two possible boundaries

- **Maven modules / Gradle subprojects** — enforced by the compiler. A context cannot
  reach into another's internals because the dependency is not declared. Strongest, and
  the right choice once a context is stable.
- **Spring Modulith** — package-level modules with `ApplicationModules.of(App.class)
  .verify()` as the check, plus generated documentation. Lighter, and a better fit while
  boundaries are still moving.

**jMolecules** (`@AggregateRoot`, `@ValueObject`, `@Repository`, `Association`) makes the
tactical roles explicit in the code rather than inferred from package names, and its
ArchUnit and Modulith integrations turn them into assertions. Where it is present, read
the annotations as the team's stated intent and audit against *that*.

## Testing note

Domain-core tests need no mocks **and no Spring**: construct real aggregates and value
objects, call methods, assert outcomes and recorded events. A domain test that needs
`@SpringBootTest`, `@MockitoBean`, or an open persistence session is evidence the
boundary is broken — flag it (see `tdd`'s `references/ddd_testing.md` and
`references/java-junit5.md`).
