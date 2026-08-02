# Java — SOLID idioms & test detection

How the five principles translate into *modern* Java (21+, this project targets 25).
The wrong way to apply SOLID here is to write 2005 Java: `IFoo` naming, an
`AbstractFooFactory` per variant, and a class hierarchy where a sealed interface or a
function would do. Records, sealed types and pattern matching removed most of the
ceremony that gave these principles their bad reputation in this language.

The other wrong way is Spring-specific: **the container makes wiring free, which makes
a DIP violation invisible.** A field-injected god service compiles, starts, and passes
its `@SpringBootTest` — the design smell shows up only as a test that cannot be written
without the framework.

## Per-principle idioms

**SRP** — split at class level; package-private classes cost nothing, so a package may
hold one public type and several collaborators without widening any API. A god
`@Service` usually becomes: a domain class holding the rule + a repository port + a
notifier port, wired in a `@Configuration` composition root. `record` for data-shaped
things. Resist the "one class per layer per entity" reflex — `UserService` /
`UserManager` / `UserHelper` is three names for one responsibility, not three.

**OCP** — prefer, in order of ceremony:
1. **Sealed interface + pattern-matching `switch`** when the variant set is *closed*.
   The compiler checks exhaustiveness, so adding a variant produces a compile error at
   every site that must handle it. This inverts OCP's usual guarantee and is better for
   a closed set: you *want* to be told, not to silently fall through a default.
2. **`Map<Key, Function<…>>` dispatch** when the set is open and the variants are
   stateless — adding one is adding an entry.
3. **Spring's collection injection** when the set is open and the variants are beans:
   declaring `List<PricingRule>` or `Map<String, PaymentHandler>` as a constructor
   parameter makes the container collect every implementation, so adding a variant is
   adding a `@Component` and touching nothing else. Order with `@Order` only if order
   is part of the contract.
4. **Strategy objects** only when variants carry state or configuration.

Choosing 1 versus 2/3 is a real decision, not a style preference: sealed is *closed for
extension by design*, which is correct for a domain union (payment outcomes, order
states) and wrong for a plugin set.

**LSP** — the base contract lives in the interface's Javadoc and its types; overrides
honor both. The classic Java violation is an override that throws
`UnsupportedOperationException` — the JDK itself ships it in
`Collections.unmodifiableList`, which is why it reads as acceptable and is not. Also
watch: an override adding validation the base did not require (strengthened
precondition), returning `null` where the base returns an empty collection, and
`equals`/`hashCode` symmetry breaking across a subclass that adds a field. Covariant
return types are legal and fine. Prefer composition to extending a concrete class for
reuse — inheritance for code sharing is where most LSP findings originate.

**ISP** — small interfaces, defined next to the **client** that needs them, carrying
only the methods that client calls. `@FunctionalInterface` is ISP at its limit and
often the honest size. Java's `default` methods let an interface grow without breaking
implementors — that is a migration tool, not a licence to keep adding; an interface
whose implementors leave half the defaults untouched is already segregated in practice
and should be split in fact.

**DIP** — constructor injection with a port-typed parameter. Spring autowires a
single-constructor bean implicitly, so `@Autowired` is noise:

```java
@Service
public class OrderService {

    private final OrderRepository orders;     // a port this package declares
    private final Clock clock;

    public OrderService(OrderRepository orders, Clock clock) {
        this.orders = orders;
        this.clock = clock;
    }
}
```

The findings, in rough order of how often they appear:

- **`@Autowired` on a field** — the dominant Java DIP violation. The field cannot be
  `final`, the class lies about what it needs, and no test can construct it without
  reflection or a container. Setter injection has the same defect plus mutability.
  This is a Critical finding wherever the class holds domain logic.
- **`ApplicationContext.getBean(...)`, or a static accessor to a bean** — a service
  locator: the dependency is real but invisible in the signature, and there is no seam.
- **`Instant.now()` / `LocalDate.now()` inside domain code** — a hidden dependency on
  the system clock that no test can control. Inject `java.time.Clock`; it exists for
  exactly this and is a one-line `Clock.fixed(...)` in a test.
- **Depending on `JpaRepository<User, Long>` rather than a `UserRepository` port** —
  the domain now depends on Spring Data and its whole method-name query language.
- **Scattered `@Value("${...}")` strings** — bundle them into a
  `@ConfigurationProperties` record and inject that one object.

JDK types (`String`, `List`, `BigDecimal`) are not dependencies to invert. `Clock`,
`Random`, the filesystem and anything doing I/O are.

## Test suite detection

| Signal | Suite / command |
|--------|-----------------|
| `pom.xml` with `spring-boot-starter-test` or a surefire config | `./mvnw test`; **`./mvnw verify`** when failsafe (`*IT`) tests exist |
| `build.gradle[.kts]` with `useJUnitPlatform()` or the JVM Test Suite plugin | `./gradlew test` (`./gradlew build` for the full gate) |
| Multi-module reactor / Gradle subprojects | scope the inner loop: `-pl <module> -am`, or `:module:test` |
| `Makefile` / `justfile` with a `test` target, or a CI workflow | whatever it runs — the project's declared truth wins over inference |

Always invoke through the wrapper (`./mvnw`, `./gradlew`), never an ambient `mvn` or
`gradle`: the wrapper pins the build tool version the way a lockfile pins dependencies.
Record the exact command and run it from the repository root.

**Light verification mode** (no suite): `./mvnw -q compile` or `./gradlew compileJava`;
`./mvnw -q -DskipTests package` to prove it still assembles; run Error Prone, SpotBugs
or Checkstyle if the build already configures them; `./mvnw dependency:analyze` to
catch a used-but-undeclared dependency the compile happened to resolve transitively.

**A note on ArchUnit.** DIP and ISP are the two principles a machine can actually check
here — "no class in `..domain..` depends on `org.springframework..`" is one ArchUnit
rule, and it runs as a JUnit test in the normal suite. Detect whether the project
already has ArchUnit rules and read them before writing findings; they encode the
boundaries the team believes in. Proposing new ones is `/clean-architecture`'s job, not
this lens's — see that skill's `java.md`.
