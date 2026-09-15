# DDD in Java — concrete idioms

The tactical patterns from `ddd-core.md`, rendered in idiomatic Java (21+, this project
targets 25). Other languages fall back to the core reference.

**Spring baseline: Boot 4.x, Hibernate 6.2+.** Both matter here: Boot 4.0 removed
`@MockBean`/`@SpyBean` and relocated the test-slice packages (see
`tdd/references/java-junit5.md`), and the record-`@Embeddable` support discussed below
landed in Hibernate 6.2 — auditing against an older assumption produces false findings.

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
| **Domain base** | shared behavior *inside* the domain | `AggregateRoot`, `DomainEvent` | **`abstract class`**, or a sealed interface |

`Specification` is the documented exception — its combinators are `default` methods over
one abstract method, so it stays an interface; see its section below.

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

- a **no-arg constructor** — so the object can exist in a state the invariants forbid,
  and the compact-constructor validation above has no equivalent. Jakarta Persistence
  requires it to be public or protected; **Hibernate is laxer** and accepts
  package-private, needing only package visibility for runtime proxy generation. Prefer
  package-private and know you have traded spec portability for encapsulation;
- **non-final fields**, because with field access the provider writes state directly
  after no-arg construction — this is about field access, not proxies;
- a **non-final class** for lazy proxying. Hibernate does not *reject* a final entity
  class; it degrades, losing proxy-based lazy fetching for associations to it. Flag it
  as a performance-tuning constraint, not as a bar;
- **records are not permitted as entities at all** — they are final and have no no-arg
  constructor.

Records *are* fine as `@Embeddable`, and this is where a stale claim does real damage:
**Hibernate has supported record embeddables natively since 6.2** (2023). A custom
`@EmbeddableInstantiator` is only needed for non-record classes that do not follow bean
conventions. Auditing a plain `@Embeddable record Money(...)` as broken, or pushing an
instantiator into code that does not need one, is a false finding.

So annotating an aggregate `@Entity` forces you to surrender immutability, construction
invariants, and the value-object idiom in the same stroke. Lazy loading compounds it: the
"aggregate" only functions with a stateful `Session` open, so it is not whole in memory
and a method on it can throw `LazyInitializationException` in production and never in a
test. That is not a proxy-only hazard — uninitialized collections raise it too, and with
bytecode enhancement so do lazy basic attributes. The condition is an open session, not
the presence of a proxy.

Three resolutions, in order of how often they are right:

1. **Use Spring Data JDBC instead of JPA.** It is designed around aggregates: it loads
   and stores a whole aggregate, has no lazy loading, no dirty tracking and no session,
   works with immutable types and constructor binding, and models cross-aggregate
   references as `AggregateReference` rather than an object graph. Where the team is
   still choosing, this is the recommendation — most of this section's problem simply
   does not arise.

   Two costs to state rather than discover. **`save()` on an existing aggregate deletes
   and reinserts its children**, so child-row identities are not stable across updates —
   fine for a true aggregate, wrong if something outside holds references to those rows.
   And **`isNew` detection defaults to "id is null or zero"**, which **collides directly
   with the application-generated identity this file recommends above**: an `OrderId`
   minted before persistence makes a genuinely new aggregate look existing, and `save()`
   issues an UPDATE that affects zero rows. Resolve it deliberately — add `@Version`,
   implement `Persistable`, or call `JdbcAggregateTemplate.insert()` explicitly. Do not
   adopt both recommendations without picking one of those three.
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

### Collection- vs persistence-oriented — Java makes the choice for you

Java is the clearest illustration of the two styles in `ddd-core.md`, because the
persistence technology decides:

- **JPA/Hibernate is collection-oriented by nature.** A managed entity loaded in a
  transaction is dirty-checked and flushed at commit — `save()` on an already-managed
  aggregate is a no-op that many teams write anyway, believing it is what persists the
  change. It is not, and that misunderstanding is worth a finding on its own: the
  transaction boundary, not the `save` call, is what commits.
- **Spring Data JDBC is persistence-oriented.** No session, no dirty tracking; the
  aggregate is written when, and only when, `save()` is called. This is the style the
  "anemic-model trap" section recommends, and it pairs with the `isNew`/application-
  generated-identity caveat noted there.

A codebase that mixes both — some aggregates relying on dirty checking, others on an
explicit `save` — will lose writes at exactly the seams nobody tests. Name the style
once, in `docs/domain/model.md`, and audit against it.

## Specification — composable business rules

```java
@FunctionalInterface
public interface Specification<T> {

    boolean isSatisfiedBy(T candidate);

    default Specification<T> and(Specification<T> other) {
        return candidate -> isSatisfiedBy(candidate) && other.isSatisfiedBy(candidate);
    }

    default Specification<T> or(Specification<T> other) {
        return candidate -> isSatisfiedBy(candidate) || other.isSatisfiedBy(candidate);
    }

    default Specification<T> negate() {
        return candidate -> !isSatisfiedBy(candidate);
    }
}

var eligibleForFreeShipping =
        new OrderOverThreshold(new Money(5000, Currency.getInstance("EUR")))
                .and(new ContainsHazardousGoods().negate());
```

Java is the one language here where the *interface with `default` methods* is the right
carrier rather than an abstract class: the combinators close over `this` and need no
state, so a single abstract method keeps every specification implementable as a lambda.
This is the documented exception to the "a `default` body means you wanted an abstract
class" rule above — the defaults here are combinators over the single abstract method,
not shared implementation state.

### The repository-translation seam

Spring Data ships this seam pre-built: `JpaSpecificationExecutor` takes an
`org.springframework.data.jpa.domain.Specification`, which is a Criteria-API builder,
not a domain predicate. **Do not let that type into the domain** — it drags
`jakarta.persistence.criteria` inward and inverts the dependency arrow. Keep the domain
`Specification<Order>` above, add `List<Order> matching(Specification<Order>)` to the
`OrderRepository` port, and translate in the adapter:

```java
@Repository
class JpaOrderRepository implements OrderRepository {

    private final SpringDataOrderRepository orders;    // extends JpaSpecificationExecutor<OrderRecord>

    JpaOrderRepository(SpringDataOrderRepository orders) {
        this.orders = orders;
    }

    @Override
    public List<Order> matching(Specification<Order> specification) {
        return orders.findAll(toCriteria(specification))   // returns Spring Data's Specification
                     .stream().map(OrderRecord::toDomain).toList();
    }
}
```
(Java has no import aliasing, so one of the two must be fully qualified at every use —
a small, permanent tax that is itself an argument for naming the domain type
`OrderRule` instead.)

`toCriteria` handles the finite set of domain specifications this adapter can render and
throws on the rest — an explicit `UntranslatableSpecificationException` beats a silent
`findAll()` plus in-memory filter.

One design fork worth stating rather than stumbling into: **sealing the hierarchy makes
the translator's `switch` exhaustive at compile time, and gives up lambdas** — a
`sealed interface` cannot be implemented by a lambda, so `@FunctionalInterface` must
come off (it is a compile error on a sealed type) and `and`/`or`/`negate` must return
small `Composite` records instead of lambdas. That is usually the better trade for a
*translated* specification — the compiler catches the rule you forgot to render — and
the worse one for purely in-memory rules. Pick per hierarchy, not per codebase.

Java's fork is the same one TypeScript faces (class-with-combinators vs tagged union):
in-memory composability and translatability pull against each other, and the sealed
version is how you buy both, at the cost of a named type per rule.

## Transactions are the unit of work

Java's unit of work is `@Transactional`, and it belongs on the **application service** —
not on the aggregate, which must not know that persistence exists.

Not on the repository either, though the usual reason given for that is wrong. Spring
Data repositories are *already* transactional (`SimpleJpaRepository`), and under the
default `REQUIRED` propagation they **join** the caller's transaction rather than
committing separately — all of it one physical transaction, committed once at the outer
boundary. Spring's own reference endorses that layering. The real argument is about
guarantees: with `@Transactional` only on the repository, each call becomes its own
outermost transaction *when no service transaction exists*, so the aggregate boundary
holds by accident rather than by declaration. Put it on the application service and the
boundary is stated.

Domain events **handle** after commit, which Spring expresses directly:

```java
@Component
class OrderPlacedHandler {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPlaced event) { … }
}
```

`AFTER_COMMIT` is the default `TransactionPhase`, so stating it is documentation rather
than configuration. Two traps that are not: **writes performed in an AFTER_COMMIT
listener are silently discarded** unless the listener opens a new transaction
(`REQUIRES_NEW`) — the original transactional resource is already committed — and with
**no** active transaction the listener is not invoked *at all* unless
`fallbackExecution = true`, which is how events vanish in tests that do not run
transactionally.

Spring Data's `AbstractAggregateRoot` automates the recording half: call
`registerEvent(...)` inside the aggregate and the repository publishes on save
(`@DomainEvents` / `@AfterDomainEventPublication`). **Publication happens
synchronously inside `save()`, before the transaction commits** — only the *handling* is
deferred, and only if the listener is `@TransactionalEventListener`. Do not read
`AbstractAggregateRoot` as giving after-commit semantics by itself.

Two more sharp edges: the publishing interceptor triggers on single-parameter methods
whose name **starts with `save`** (`save`, `saveAll`, `saveAndFlush`) plus an **exact**
list of four deletes — `delete`, `deleteAll`, `deleteInBatch`, `deleteAllInBatch`. The
asymmetry is the trap: `save` is prefix-matched, `delete` is not, so **`deleteById(...)`
and `deleteAllById(...)` publish nothing** despite looking like they should. And the base class
extends a Spring type, putting a framework dependency in the domain: a Dependency-Rule
trade-off the team may accept, but flag it as one.

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

The guarantee is **compile-time only**, which matters across module boundaries: a switch
site that is not recompiled after a permitted subtype is added throws `MatchException` at
runtime instead of failing to build. Adding to a sealed hierarchy is binary-incompatible
in practice — recompile every consumer, or treat the addition as a breaking change.

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
