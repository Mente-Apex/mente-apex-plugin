# Java Adapter — JUnit 5

Stack-specific mechanics for the core TDD cycle. The cycle itself lives in SKILL.md;
this file covers how to execute it in a Java project. Assertions are **AssertJ** and
test doubles are **Mockito** — both arrive with `spring-boot-starter-test`, so in a
Spring project they are already on the classpath and need no decision. **JUnit 6 is
near-identical** for everything below; see the compatibility note at the end.

**Spring baseline: Boot 4.x.** This matters more than it looks. Boot 4.0 **removed**
`@MockBean` and `@SpyBean` (not merely deprecated them — that was 3.4) and **relocated
most test-slice annotations into new packages**: `@DataJpaTest` is now
`org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest`, `@WebMvcTest` is
`org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest`, and
`@AutoConfigureTestDatabase` is `org.springframework.boot.jdbc.test.autoconfigure…`.
Code written against 3.x imports will not compile. Detect the Boot generation from the
build file before writing a single test, and where a project is still on 3.x, use
`@MockitoBean` anyway — it exists from Spring Framework 6.2 and is correct on both.

## Discovering conventions

Check, in order:

1. **Build tool and its test config** — `pom.xml` (surefire/failsafe `<configuration>`,
   `<properties>` for `maven.compiler.release`) or `build.gradle[.kts]` (the `test`
   task, `useJUnitPlatform()`, toolchain block). Note excluded groups, custom
   `@Tag` filters, and system properties before running anything.
2. **Layout is not a choice.** Both build tools mandate `src/test/java` mirroring
   `src/main/java` package-for-package, with fixtures in `src/test/resources`. Unlike
   Python or TypeScript there is no co-location variant to detect — if tests live
   anywhere else, someone has overridden the source sets and you need to read how.
3. **Naming decides what runs.** Surefire collects `*Test`, `Test*`, `*Tests`,
   `*TestCase`; failsafe collects `*IT`, `IT*`, `*ITCase` and runs them in `verify`,
   not `test`. A test class named outside those patterns is silently never run — the
   single most common "my test passes" illusion in Maven projects. Gradle collects
   whatever the platform discovers, so a class Maven ignores may run under Gradle,
   and the same suite disagrees with itself across the two.
4. **Shared setup** — look for `@TestConfiguration` classes, a `src/test/java/.../support`
   package, existing `@Container` singletons, and JUnit extensions registered via
   `@ExtendWith` or `META-INF/services`. The fixture you need may already exist.
5. **How tests are run** — always through the wrapper, `./mvnw` or `./gradlew`, never a
   globally-installed `mvn`/`gradle`. The wrapper pins the build tool version the same
   way a lockfile pins dependencies; running the ambient one is this ecosystem's
   equivalent of installing outside the project environment.

Greenfield defaults: `src/test/java`, one test class per production class named
`<ClassName>Test`, `@Nested` classes for grouping, AssertJ's `assertThat`.

During the cycle, run the single new test first, then the full suite:

```bash
# Maven
./mvnw test -Dtest='UserRepositoryTest#storesAndRetrievesAUser'
./mvnw verify                     # full suite, incl. failsafe integration tests

# Gradle
./gradlew test --tests 'com.example.UserRepositoryTest.storesAndRetrievesAUser'
./gradlew build
```

**Gradle's up-to-date check, and what it can and cannot hide.** A **failed task is never
marked up-to-date**, so a red step always re-runs — Gradle will not turn red into green,
and in the red-green loop editing a test changes the inputs anyway. The reachable hazard
is the opposite one: **untracked inputs**. A test that depends on something Gradle cannot
see — a file outside the project tree, an environment variable, an external service —
leaves `:test UP-TO-DATE` and reports the *previous* run's success on a suite that is
now actually red. Use `./gradlew test --rerun` (single task) when you need to trust a
step whose inputs Gradle does not track; `--rerun-tasks` re-runs everything and is
almost always more than you want.

**Refactor jobs on a large suite — two-tier running.** A full `./mvnw verify` on a
multi-module Spring project is minutes, not seconds, and paying it after the Primary
and after every rider is what makes a big-repo apply crawl. For the *inner* checks,
scope down:

- Maven — `-Dtest='Pattern*Test'` to select by name, and `-pl <module> -am` to build
  only the changed module plus what it depends on. Add `-o` (offline) once the
  dependencies have resolved once. **Failsafe uses `-Dit.test`, not `-Dtest`** — a
  detail that matters precisely because `verify` is the end gate below, and
  `-Dtest=` silently selects nothing among the integration tests. (Maven's own
  single-test docs still scope `-Dtest` to JUnit 4 and TestNG; it does work with the
  JUnit Platform provider, but nothing official blesses it, so verify it runs what you
  think on the project in front of you.)
- Gradle — `:module:test` for one subproject, `--tests` for one class or method.
  Gradle's build cache and up-to-date checks already skip unchanged modules.

Then run the **full `test_command` once as the job's end gate** — it is what catches a
breakage in a distant module the subset never touched, and it must be green before the
job is reported `applied`. In Maven, that end gate is `verify`, not `test`: skipping
failsafe means skipping every integration test, which is exactly where a
cross-module breakage surfaces.

## Constructor injection is the test seam

A class that takes its collaborators as constructor parameters gets a one-line setup.
A class that `new`s its own repository, or reaches into a static factory, needs
`mockStatic` or a Spring context to test at all — which is the design smell the
REFACTOR checklist tells you to fix, not to work around.

```java
class UserRepositoryTest {

    private final UserRepository userRepository = new InMemoryUserRepository();

    @Test
    void storesAndRetrievesAUser() {
        var user = new User("Alice", "alice@example.com");

        userRepository.add(user);

        assertThat(userRepository.findByEmail("alice@example.com")).contains(user);
    }
}
```

**Domain tests use no Spring.** No `@SpringBootTest`, no `@ExtendWith(SpringExtension.class)`,
no context at all — a plain JUnit class constructing plain objects. If a domain test
needs the container to run, the domain depends on the framework and the dependency
rule is already broken; that is a finding, not a setup problem. Spring's test
annotations belong to adapter tests only (see below, and `ddd_testing.md`).

**`@InjectMocks` is a smell, not a convenience.** It exists to populate collaborators
reflectively, including into private fields — which means it works just as well on a
class with no injection seam at all, and so hides the design problem the seam was
meant to expose. Construct the subject yourself and pass the mocks in:

```java
@ExtendWith(MockitoExtension.class)
class RegistrationServiceTest {

    @Mock private UserRepository userRepository;      // a port, not a concretion
    @Mock private EmailSender emailSender;

    private RegistrationService registrationService;

    @BeforeEach
    void setUp() {
        registrationService = new RegistrationService(userRepository, emailSender);
    }
}
```

Mock **ports you own the interface to**, never concrete framework classes. Needing
`mockStatic`, `mockConstruction`, or a Mockito inline agent to test something is the
signal that a dependency should have been injected.

## Expected exceptions

AssertJ's fluent form carries the type and the message in one chain:

```java
@Test
void rejectsADuplicateEmail() {
    userRepository.add(new User("Alice", "alice@example.com"));

    assertThatThrownBy(() -> userRepository.add(new User("Bob", "alice@example.com")))
            .isInstanceOf(DuplicateEmailError.class)
            .hasMessageContaining("already exists");
}
```

JUnit's own `assertThrows` returns the exception, which is better when you need to
assert on more than the message:

```java
var error = assertThrows(DuplicateEmailError.class, () -> userRepository.add(duplicate));
assertThat(error.conflictingEmail()).isEqualTo("alice@example.com");
```

Assert on the exception **type**, not a substring of the message, unless the message
is itself the contract. `isInstanceOf` accepts subclasses; use `isExactlyInstanceOf`
when the precise type is the specification.

## Table-driven variations — `@ParameterizedTest`

```java
@ParameterizedTest
@ValueSource(strings = {"", "noatsign", "@nodomain", "spaces in@email.com"})
void rejectsInvalidEmail(String invalidEmail) {
    assertThatThrownBy(() -> new User("Test", invalidEmail))
            .isInstanceOf(ValidationError.class);
}
```

`@ValueSource` for one primitive argument, `@CsvSource` for several, `@MethodSource`
for anything needing real objects, `@EnumSource` for an enum's constants.

**`@EnumSource` is a convenient default, not a check.** `@EnumSource(Status.class)`
resolves at runtime to every constant declared *at that moment*, so a constant added
later is picked up automatically — but nothing fails if coverage is incomplete, and the
`names = {...}` form silently omits anything added after it was written. Do not read it
as the compile-time exhaustiveness a `switch` over a sealed type gives you; that one is
enforced by the compiler, this one is a runtime convenience, and conflating them is how
a "covered" enum quietly grows an untested case.

Use a parameterized test when testing the *same behavior* with different inputs.
Distinct behaviors get distinct tests — cramming them into one `@CsvSource` hides
which specification broke. In the one-test-at-a-time cycle, a parameterized test
counts as one test *method* but each row is a separate reported test: introduce it
with one row, make it pass, then add rows one at a time.

## Useful built-ins before reaching for anything else

- `@Nested` — inner classes grouping tests that share setup, and the idiomatic way to
  express "given this state, these behaviors". Reads far better than a flat class of
  thirty methods with `given…` prefixes in their names.
- `@DisplayName` — a readable sentence for the report. Prefer a method name that
  already reads as a specification and skip the annotation; reach for it when the
  sentence genuinely needs punctuation or spaces.
- `@TempDir` — per-test temporary directory, injected as a parameter or field. Never
  write test files into the repo tree.
- `assertAll(...)` — reports every failed assertion in a group instead of stopping at
  the first, which matters when asserting several fields of one result.
- `@Tag` — mark slow or integration-flavoured tests so the inner loop can exclude
  them (`-DexcludedGroups=slow`, or Gradle's `useJUnitPlatform { excludeTags("slow") }`).
- Text blocks for expected JSON/SQL, and `record` for throwaway test fixtures — both
  remove more noise from a Java test than any library does.

## Spring Boot — slices, not the whole context

`@SpringBootTest` starts the entire application context. It is the right tool for a
handful of wiring tests and the wrong one for everything else: it is slow enough to
break the red-green rhythm, and it passes for reasons unrelated to the code under
test. Reach for the narrowest slice that exercises the boundary:

| Annotation | Loads | Use for |
|---|---|---|
| *(none)* | nothing | domain and application logic — the default |
| `@WebMvcTest(Controller.class)` | one controller + MVC infrastructure | HTTP mapping, status codes, serialization |
| `@DataJpaTest` | JPA, repositories, a test datasource | mapping and query correctness |
| `@JsonTest` | the object-mapper slice — `@JacksonComponent` beans, `JacksonModule`s, and injected `JacksonTester` fields | (de)serialization contracts |
| `@SpringBootTest` | everything | wiring, and only wiring |

On Boot 4.x, `@SpringBootTest` also needs an explicit `@AutoConfigureMockMvc` before
`MockMvc` is available — it is no longer implied.

`@MockitoBean` replaces a bean in the slice's context. `@MockBean` was deprecated in
Boot 3.4 and **removed in Boot 4.0**, so it is not a legacy-but-working alternative.
Two behaviours worth knowing: the default override strategy is `REPLACE_OR_CREATE`, so
it *creates* the bean when none exists unless you set `enforceOverride = true` — a typo
in a bean name silently gives you a mock of nothing rather than a failure — and it is
not supported on `@Configuration` classes.

It is a container-level operation, so it is correct in a slice test and wrong in a
domain test, where a constructor parameter does the same job with no framework involved.

For adapter tests that need a real database, `@ServiceConnection` wires the container
into Spring's datasource properties with no manual URL plumbing:

```java
@DataJpaTest
@Import(PostgresContainerConfig.class)     // container declared as a Spring bean
class JpaUserRepositoryTest { }

@TestConfiguration(proxyBeanMethods = false)
class PostgresContainerConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        return new PostgreSQLContainer<>("postgres:17");
    }
}
```

**Prefer this to `@Testcontainers` + `@Container`.** Spring explicitly recommends
against the JUnit extension here: it stops the container when the test class finishes,
while Spring's TestContext framework caches the `ApplicationContext` beyond that point,
so a later test or a bean destruction callback can fail against a container that is
already gone. Declaring the container as a bean lets the context own its lifecycle.

`@AutoConfigureTestDatabase(replace = NONE)` is **not needed** alongside
`@ServiceConnection` on Boot 3.4+: the default became `Replace.NON_TEST`, which
explicitly recognises Testcontainers-sourced databases. Seeing it in a codebase usually
dates the test rather than doing anything. (If you ever do need the old behaviour, it is
`Replace.AUTO_CONFIGURED`, not `NONE`.)

Write these only when the mapping is the thing under test — per the core cycle, adapter
integration tests are on request, not by default.

## JUnit 6 compatibility

JUnit 6 (baseline Java 17) keeps the Jupiter **programming model** unchanged: `@Test`,
`@Nested`, `@ParameterizedTest`, `assertThrows` and every annotation above are
identical, and AssertJ and Mockito are unaffected. So the tests you write here are the
same tests either way.

The *migration*, though, is more than a version bump, and three items bite:

- **`junit-platform-runner` was removed with no replacement** — a suite still using the
  JUnit 4 `@RunWith(JUnitPlatform.class)` bridge has nowhere to go but rewriting it.
- **The parameterized CSV engine swapped from univocity to FastCSV**, which can turn a
  passing `@CsvSource` test red with no prior deprecation warning. Quoting and escaping
  edge cases are where it shows.
- **Platform artifacts renumbered 1.x → 6.x**, so hand-pinned versions across
  `junit-platform-*` and `junit-jupiter-*` will disagree. Use `junit-bom` and let it
  align them.

The real cost, though, is usually the **Java 8 → 17 baseline jump** rather than any of
the above. Vintage is still available but deprecated. Detect the version from the build
file rather than assuming, and follow whichever the project resolves.
