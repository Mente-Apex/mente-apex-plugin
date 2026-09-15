# Java — clean-code idioms

The standard ([docs/clean-code-standard.md](../../../docs/clean-code-standard.md)) is
the rubric; this file is what its principles look like in *modern* Java (21+, this
project targets 25, Spring Boot 4.x), and where applying them literally writes 2005 Java.

The failure mode here is ceremony. Records, sealed types, pattern matching and `var`
removed most of the boilerplate that gave these principles their reputation in this
language — a finding that adds a factory, an interface and an abstract base where a
record and a switch would do is a finding that made the code worse.

## Naming

- **No `IFoo`, no `FooImpl`.** `FooImpl` as the only implementation of `Foo` means the
  interface was invented for a second implementation that never arrived — that is a
  `solid`/`clean-architecture` finding about a speculative seam, and a naming finding
  here.
- **`get`/`set` are not mandatory.** A record's accessor is `amount()`, and that reads
  better than `getAmount()`. Do not file a record accessor as a naming violation.
- **`var` where the type is on the line already.** `var orders = new ArrayList<Order>()`
  is clearer than the repeated generic; `var result = service.process()` is not.

## Types and data

- **A record for data, always, unless it needs identity or mutation.** A 40-line class
  with a constructor, five getters, `equals`, `hashCode` and `toString` is one line as a
  record, and five fewer places to forget a field.
- **Sealed interface + records + `switch` pattern matching** instead of a visitor or an
  enum-plus-`if` ladder. The compiler checks exhaustiveness, which is the whole point.
- **`Optional` is a return type, not a field and not a parameter.** `Optional` fields
  serialize badly and add a wrapper to every read; an `Optional` parameter means the
  method has two behaviours and wants to be two methods.

## Functions

- **Boolean parameters are unreadable at the call site.** `process(order, true, false)`.
  Two methods, or an enum, or a record of options.
- **A stream chain longer than about five operations wants a name**, not another
  `.map`. Extract the predicate or the mapper to a named method and the chain reads as
  prose.
- **Do not reach for a stream where a for-loop is clearer** — particularly with an index,
  early exit, or a side effect. `forEach` on a stream to mutate something outside it is a
  loop wearing a costume.

## Errors

- **Never an empty `catch`.** And never `catch (Exception e) { log.error(e); }` at a
  layer that cannot do anything about it — that is swallowing with extra steps, and it
  turns one failure into a log line nobody reads.
- **Checked exceptions stop at the boundary.** Wrapping a checked exception in an
  unchecked one at the adapter edge is right; propagating `throws SQLException` up
  through the domain is a Dependency-Rule violation `clean-architecture` will also file —
  cross-reference, file once.
- **Always chain the cause.** `throw new OrderFailed(msg, cause)`. A lost cause is a lost
  afternoon.
- **`Objects.requireNonNull` at a public entry point** documents and enforces in one line.

## Spring-specific (Boot 4.x)

- **Constructor injection, never field injection.** `@Autowired` on a field makes the
  class untestable without the container and hides how many collaborators it has — the
  count is the SRP evidence, and field injection erases it.
- **`@Value` scattered through a class is configuration smeared across the codebase.**
  `@ConfigurationProperties` on a record collects it into one typed thing.
- **A `@Transactional` method calling another method on `this` does not start a
  transaction.** The proxy is bypassed. This is a defect, not a style point.
- **Boot 4.0 removed `@MockBean`/`@SpyBean`** and relocated the test-slice packages; if a
  finding leads you to write a test, read `tdd/references/java-junit5.md` first.

## Where this bends

- **Builders earn their place** past ~4 constructor parameters or with optional fields —
  this is the one place Java ceremony pays. Don't file a builder as over-engineering when
  the alternative is a seven-argument constructor.
- **A package-private class is not "missing an interface".** It is scoped, which is
  better.
- **Getters on an entity are not automatically anemic.** That judgement is `ddd`'s, over
  the whole aggregate; this lens should not make it from one file.
