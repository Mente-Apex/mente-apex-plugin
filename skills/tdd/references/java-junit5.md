# Java Adapter — JUnit 5

Stack-specific mechanics for the core TDD cycle. The cycle itself lives in SKILL.md;
this file covers how to execute it in a Java project. Assertions are **AssertJ** and
test doubles are **Mockito** — both arrive with `spring-boot-starter-test`, so in a
Spring project they are already on the classpath and need no decision. **JUnit 6 is
near-identical** for everything below; see the compatibility note at the end.

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

**Gradle's up-to-date check can hide a RED step.** If the test task's inputs have not
changed, Gradle prints `UP-TO-DATE` and reuses the previous result — so a test you
expected to fail can report the last run's success. In the red-green loop the inputs
do change on every edit, but when you need certainty (re-running an unchanged test to
confirm it still fails for the reason you think), use `./gradlew test --rerun` rather
than trusting the cache.

**Refactor jobs on a large suite — two-tier running.** A full `./mvnw verify` on a
multi-module Spring project is minutes, not seconds, and paying it after the Primary
and after every rider is what makes a big-repo apply crawl. For the *inner* checks,
scope down:

- Maven — `-Dtest='Pattern*Test'` to select by name, and `-pl <module> -am` to build
  only the changed module plus what it depends on. Add `-o` (offline) once the
  dependencies have resolved once.
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
for anything needing real objects, `@EnumSource` to cover every constant of an enum
(the one case where exhaustiveness is checked for you).

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
| `@JsonTest` | serializers only | (de)serialization contracts |
| `@SpringBootTest` | everything | wiring, and only wiring |

`@MockitoBean` replaces a bean in the slice's context (it superseded `@MockBean`,
deprecated from Spring Boot 3.4). It is a container-level operation, so it is
correct in a slice test and wrong in a domain test, where a constructor parameter
does the same job with no framework involved.

For adapter tests that need a real database, Testcontainers with `@ServiceConnection`
wires the container into Spring's datasource properties with no manual URL plumbing:

```java
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class JpaUserRepositoryTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:17");
}
```

Declare the container `static` so one instance is shared across the class rather than
started per test method. Write these only when the mapping is the thing under test —
per the core cycle, adapter integration tests are on request, not by default.

## JUnit 6 compatibility

JUnit 6 (baseline Java 17) keeps the Jupiter programming model unchanged: `@Test`,
`@Nested`, `@ParameterizedTest`, `assertThrows`, and every annotation above are
identical, and AssertJ and Mockito are unaffected. What moves is packaging and
baseline — the `junit-jupiter` aggregate coordinates and the platform version — so a
migration is a dependency bump plus removal of anything already deprecated in JUnit
5.x, not a rewrite of tests. Detect the version from the build file rather than
assuming, and follow whichever the project resolves.
