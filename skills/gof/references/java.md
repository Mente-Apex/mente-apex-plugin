# Java — GoF idioms & test detection

How the 23 patterns translate into *modern* Java (21+, this project targets 25). Java is
the language the GoF catalogue was popularized in, which makes it the one language where
the textbook forms are literally correct — and that is the trap. **Records, sealed types,
lambdas and the Spring container have each absorbed patterns that used to need a class
hierarchy.** Writing the 1994 form when the language now has a keyword for it is
over-engineering, and it grades down exactly as readily as a broken implementation.

Two Java-specific lenses to apply throughout:

- **Spring may already be the pattern.** A `@Component` is a Singleton, `@Transactional`
  is a Decorator, the security filter chain is a Chain of Responsibility. Hand-rolling
  one inside a Spring application is usually a finding, not an implementation.
- **A pattern that exists to work around a missing language feature is dead here.**
  Visitor is the clearest case; see below.

## Per-pattern idioms

### Creational

**Singleton** — `enum Singleton { INSTANCE; }` is the canonical Java form (Bloch Item 3):
thread-safe, serialization-safe and reflection-safe for free. The lazy alternative is the
holder idiom (`private static class Holder { static final X INSTANCE = new X(); }`),
which the JVM's class-initialization guarantees make safe with no synchronization.
Double-checked locking is correct **only** with a `volatile` field — grade D without it,
since the bug is invisible until a race in production.

In a Spring application, almost every hand-rolled Singleton is a finding: the container
already provides one instance with an injection seam, and the hand-rolled version
replaces that seam with a static call nothing can substitute in a test. Note the DIP
tension recorded in the `lens-overlap` map — SOLID prefers injection over any singleton,
so weigh both lenses before recommending one.

**Factory Method** — a static factory (`Money.of(...)`, `Duration.ofSeconds(...)`,
`EnumSet.copyOf(...)`) is idiomatic where the GoF write-up reaches for a subclass
hierarchy: it can return a subtype, return a cached instance, and carry a name the
constructor cannot. Reserve subclass-per-product for when the subclasses genuinely differ
in *behavior* around creation.

**Abstract Factory** — an interface plus implementations, each returning a family of
related products. This is the creational pattern that still earns its hierarchy. In
Spring it is frequently replaced by injecting a `Map<String, Product>` (the container
keys every bean of the type by name) or by a `@Qualifier`-selected bean — grade an
Abstract Factory that duplicates what the container would have done for free.

**Builder** — Bloch's Builder for a type with many optional parameters; a `record` with a
generated builder past four or five components. Lombok's `@Builder` on a record is fine —
it calls the canonical constructor, so compact-constructor validation still runs. On a
mutable class carrying `@Data` it is redundant with the setters and hides that the object
is never actually immutable — grade C. Skip the `Director` unless the same multi-step
sequence is reused across several call sites.

**Prototype** — `Cloneable` and `clone()` are broken by design (Bloch Item 13): the
contract is unenforceable, the shallow/deep decision is invisible at the call site, and
`super.clone()` silently misses fields added later. Grade D for `implements Cloneable`
and recommend a **copy constructor** or a static factory. For records, derive a new value
by calling the canonical constructor with the changed component — there is no wither
syntax in the language yet.

### Structural

**Adapter** — genuinely needed here, unlike in Python: Java's nominal typing means two
types with identical method names are *not* interchangeable, so the wrapper class does
real work. This is one of the patterns to recommend without hesitation, and it is the
shape every ports-and-adapters boundary already takes.

**Bridge** — composition over inheritance; the abstraction holds an implementor
reference, injected through the constructor. Often indistinguishable from ordinary DIP,
and there is no need to name it a Bridge when it is just injection.

**Composite** — a sealed interface with record implementations, traversed by an
exhaustive `switch`. The modern form is markedly better than the classic one: the
compiler enumerates the cases rather than a `default` branch swallowing a new node type.

**Decorator** — real and common; `java.io`'s stream hierarchy is the canonical example.
But in Spring, **`@Transactional`, `@Cacheable`, `@Async` and `@Retryable` are all
Decorators implemented as proxies**, so a hand-written decorator duplicating one of those
concerns is a finding. See Proxy for the failure mode this introduces.

**Facade** — a service class presenting one coherent operation over a subsystem. Fine as
written; grade down when the "facade" is a god class that accreted rather than a
deliberate narrowing.

**Flyweight** — `Integer.valueOf`'s cache and string interning are the JDK's own
instances. Hand-rolling one is rarely worth it; recommend it only with a measurement.

**Proxy** — the whole of Spring AOP. Two mechanisms with different constraints, and the
difference explains a class of silent bugs worth checking for directly:

- **JDK dynamic proxies** need an interface; the bean is only proxyable through it.
- **CGLIB** subclasses the class — Spring Boot's default — so it **cannot proxy `final`
  classes or `final`/`private` methods**, which then silently lose their annotation's
  behavior.
- **Self-invocation bypasses the proxy entirely.** `this.doTransactionalWork()` called
  from another method of the same bean goes straight to the target, so `@Transactional`
  never applies. No warning, no exception — the transaction simply is not there.

Any of the three is a Critical finding when it lands on `@Transactional`.

### Behavioral

**Chain of Responsibility** — Servlet `Filter`, Spring Security's filter chain, and
`HandlerInterceptor` are all this pattern, already provided. Recommend a hand-rolled
chain only outside a request path.

**Command** — a `record` command plus a handler, which is also the DDD application-service
shape; or a `Runnable`/`Callable` where the command carries no data. No class hierarchy
needed.

**Interpreter** — rare and usually the wrong reach; a parser generator or an existing
expression library beats it.

**Iterator** — `Iterable`/`Iterator` are built in and `Stream` covers most traversal.
Hand-writing an `Iterator` is almost always a finding; the exception is a genuinely lazy
source over something that is not a collection.

**Mediator** — `ApplicationEventPublisher` with `@EventListener` in Spring. A hand-rolled
mediator that only routes between beans is duplicating it.

**Memento** — a `record` snapshot. Nothing else required.

**Observer** — `java.util.Observable`/`Observer` have been **deprecated since Java 9**;
an implementation using them is a finding on sight. Use Spring's event publisher, an
injected `List<Listener>` (the container collects every implementation), or the `Flow`
API / a reactive library where back-pressure matters.

**State** — a sealed interface whose implementations are the states, switched
exhaustively. Replaces the "status enum plus a nullable field per state" shape, which is
where invalid combinations come from.

**Strategy** — a `@FunctionalInterface` plus lambdas. This is the largest ceremony
reduction in the catalogue: what the book draws as an interface and three classes is one
interface and three lambdas, or one injected `List<PricingStrategy>` in Spring. Grade
down a Strategy hierarchy whose implementations are stateless one-method classes.

**Template Method** — an abstract class with a **`final`** algorithm method calling
abstract hooks. If the algorithm method is not final, a subclass can override it and
break the invariant the pattern exists to protect — that is simultaneously an LSP
violation, so grade C and cross-reference the SOLID lens. Note that Spring's `*Template`
classes (`JdbcTemplate`, `TransactionTemplate`) are named for this pattern but are closer
to Strategy-with-callback; do not cite them as examples of the classic form.

**Visitor** — **superseded.** Visitor exists to get double dispatch over a closed
hierarchy without editing it; a sealed interface plus a pattern-matching `switch` does
the same job directly, with compiler-checked exhaustiveness and no `accept`/`visit`
boilerplate. A Visitor newly written over a sealed hierarchy on Java 21+ is a finding —
recommend the switch. An existing Visitor over a non-sealed, externally-extended
hierarchy is still legitimate; say which case you are looking at.

## Test suite detection

| Signal | Suite / command |
|--------|-----------------|
| `pom.xml` with `spring-boot-starter-test` or a surefire config | `./mvnw test`; **`./mvnw verify`** where failsafe (`*IT`) tests exist |
| `build.gradle[.kts]` with `useJUnitPlatform()` or the JVM Test Suite plugin | `./gradlew test` (`./gradlew build` for the full gate) |
| Multi-module reactor / Gradle subprojects | scope the inner loop: `-pl <module> -am`, or `:module:test` |
| `Makefile` / `justfile` target, or a CI workflow | whatever it runs — the project's declared truth wins |

Always through the wrapper (`./mvnw`, `./gradlew`), never an ambient `mvn`/`gradle`.

**Light verification mode** (no suite): `./mvnw -q compile` or `./gradlew compileJava`,
then `./mvnw -q -DskipTests package` to prove it still assembles. A pattern refactor in
Java is compiler-checked to an unusual degree — an exhaustive `switch` over a sealed type
will not compile if a case is missing — so a clean build carries more evidence here than
it would in Python or TypeScript. It is still not a test run; say which one you did.
