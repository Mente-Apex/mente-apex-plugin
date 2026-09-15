# Java — test-suite idioms

The rubric ([rubric.md](rubric.md)) is what to look for; this file is what it looks like
in a JUnit 5 suite. **The standard for how a test should be written is `tdd`'s**
([../../tdd/references/java-junit5.md](../../tdd/references/java-junit5.md)) — read its
Boot 4.x baseline note before writing any test, because Boot 4.0 removed
`@MockBean`/`@SpyBean` and relocated the test-slice packages.

## Structure

- **`src/test/java` mirrors `src/main/java` package for package.** In Maven and Gradle
  this is not a convention, it is how the test source set resolves package-private
  access — a test in the wrong package silently loses it.
- **`@Nested` classes group by scenario**, and their names complete the sentence:
  `@Nested class WhenTheCardIsExpired`. A 600-line flat test class with thirty `@Test`
  methods is the Java shape of "a pile with a lid".
- **`@DisplayName` where the method name cannot carry it.** The report is what a human
  reads when the build goes red.

## Craft

- **Name as spec**: `refundIsRefusedAfterThirtyDays()`, not `testRefund2()`.
- **AssertJ over bare JUnit assertions.** `assertThat(order.total()).isEqualTo(...)`
  produces a failure message that names both values; `assertTrue(order.total() == x)`
  produces "expected true".
- **`assertThatThrownBy(...).isInstanceOf(X.class).hasMessageContaining(...)`** — an
  `assertThrows` with no message check passes on a different failure of the same type.
- **`@ParameterizedTest` over a loop.** Each case reports separately.
- **No logic in tests.** A loop or an `if` in a `@Test` is two tests wearing one
  signature.

## Spring — where most of this lens's Java findings live

- **`@SpringBootTest` on a test that needs one class is a design finding.** Booting the
  whole context to test a unit is slow *and* it hides the dependency graph: the class
  under test never had to declare what it needed. Cross-reference `solid`/`ddd`
  (constructor injection, missing ports) via the hub; file the test-side cost here.
- **Prefer the narrow slice** — `@WebMvcTest`, `@DataJpaTest` — over the full context,
  and a plain constructor call over any of them where the class has no framework
  dependency at all.
- **`@DirtiesContext` is a confession.** It says a test mutates shared state and the fix
  was to throw the context away. Expensive, and it hides the leak instead of closing it.
- **`@Transactional` on a test rolls back**, which means the test never observes what a
  real commit does — a flush-time constraint violation stays invisible.
- **`@MockBean` is gone in Boot 4.** A suite still using it is pinned to an old Boot and
  that is a finding in its own right.

## Mocking

- **Mockito on your own domain classes is the DIP smell**; at the JDBC driver, the HTTP
  client, the clock, the message broker it is correct and must not be filed.
- **`verify()` on everything is implementation-pinning.** Verify the interaction that IS
  the behaviour (the email was sent), assert the value for everything else.
- **`@Mock` fields plus `@InjectMocks` hide the constructor.** They also keep working
  when a collaborator is added, which is exactly the signal a constructor would have
  given you.
- **`lenient()` and `RETURNS_DEEP_STUBS` are smells about the design**, not the test: a
  stub that needs deep returns is reaching through an object graph Demeter already
  objected to.

## Tending

- **`@Disabled` with no reason** is an obsolete pin. With a reason and a ticket it is a
  decision; without one it is dead weight that reads as coverage.
- **A test that no longer compiles is dead** — the Java equivalent of the collection
  error, and the same clear-cut deletion, provided the symbol is gone rather than moved.
- **Assertion-free tests**: a `@Test` that calls a method and asserts nothing passes
  unless the method throws. Common in Java suites, and exactly what the mutation gate
  finds mechanically.
