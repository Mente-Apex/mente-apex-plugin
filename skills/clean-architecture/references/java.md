# clean-architecture in Java — tooling & metrics

The headline checks want the real dependency graph. Java is the best-served language
this lens supports: **`jdeps` ships with the JDK**, so a graph tool is always reachable,
and **ArchUnit expresses the Dependency Rule as a JUnit test**, so the leave-behind
contract runs in the suite the project already has — no new CI step to negotiate.

## Detect a graph tool

Try, in order:

1. **ArchUnit already in the build** — grep `pom.xml` / `build.gradle[.kts]` for
   `com.tngtech.archunit`. If present, **read the existing rules first**: they encode
   the boundaries the team already believes in, and findings that contradict them are
   an argument you have to make, not an oversight you have found.
2. **`jdeps`** — bundled with every JDK, so it needs no install. It reads **bytecode**,
   which means the project must be compiled first (`./mvnw -q -DskipTests compile` or
   `./gradlew -q compileJava`) and that the analysis sees what the code actually
   references, not just what it imports.
3. **Build-module structure** — `mvn dependency:tree` or `./gradlew :module:dependencies`
   for the reactor/subproject graph. Coarse, but see the note on module boundaries below.

Record which path succeeded. Only if the project will not compile at all do you fall to
the **degrade path**; state "agent-driven (no graph tool)" in the report.

## `jdeps` — package edges, cycles, and Instability

```bash
./mvnw -q -DskipTests compile
jdeps -verbose:package -filter:none target/classes        # Gradle: build/classes/java/main
```

`-filter:none` is load-bearing: the default filter suppresses same-archive edges, which
are exactly the intra-application edges this lens is about. Output is `from -> to` pairs
at package granularity; aggregate them to your **component** level (a component is a
sub-package tree, not a single package), drop intra-component edges, then:

- **Instability (SDP)** — `I = Ce / (Ce + Ca)` per component, where `Ce` is the count of
  distinct components it depends on and `Ca` the count that depend on it. A component
  with no cross-component edges has no denominator; treat it as maximally stable
  (`I = 0`). Report a dependency pointing from a stable component to an unstable one.
- **Cycles (ADP)** — run an SCC/DFS over the component edge set and report each cycle as
  its chain of components.

Two Java caveats worth stating in the report. `jdeps` **misses reflective and
container-mediated edges** — a bean wired by annotation, a class loaded by name, a
Spring Data repository whose implementation is generated at runtime — so it can
understate coupling in exactly the framework-heavy code this lens cares about. And it
**sees fully-qualified inline references that no `import` line records**, so it catches
edges a source-level import scan would miss. Neither tool subsumes the other; jdeps is
the better default.

## ArchUnit — the Dependency Rule as an executable contract

This is the deliverable. Draft the rules from the findings and write them to
`docs/reports/clean-architecture/DependencyRuleTest.java`; **offer** it for
`src/test/java/.../architecture/` as a committed tripwire — never commit it silently.

```java
@AnalyzeClasses(packages = "com.example", importOptions = ImportOption.DoNotIncludeTests.class)
class DependencyRuleTest {

    @ArchTest
    static final ArchRule frameworkIsADetail =
            noClasses().that().resideInAnyPackage("..domain..", "..application..")
                    .should().dependOnClassesThat().resideInAnyPackage(
                            "org.springframework..", "jakarta.persistence..", "com.fasterxml.jackson..");

    @ArchTest
    static final ArchRule dependenciesPointInward =
            onionArchitecture()
                    .domainModels("..domain.model..")
                    .domainServices("..domain.service..")
                    .applicationServices("..application..")
                    .adapter("web", "..adapter.web..")
                    .adapter("persistence", "..adapter.persistence..");

    @ArchTest
    static final ArchRule noCycles =
            slices().matching("com.example.(*)..").should().beFreeOfCycles();
}
```

`onionArchitecture()` is ArchUnit's built-in Clean Architecture check — it asserts that
adapters may reach inward and nothing may reach outward, which is the Dependency Rule
stated once rather than as a dozen `noClasses()` rules.

**On an existing codebase, freeze rather than exempt.** `FreezingArchRule.freeze(rule)`
records today's violations as an accepted baseline and fails only on *new* ones, so a
legacy project can adopt the contract on day one instead of after the refactor. That is
almost always the right first move; a rule weakened with exclusions to make it pass is a
rule that will never tighten.

**Spring Modulith**, if present, verifies module boundaries from package structure with
`ApplicationModules.of(Application.class).verify()`. Complementary to ArchUnit rather
than a replacement: it checks module encapsulation, ArchUnit checks arbitrary rules.

## Build modules are the strongest boundary available

A Maven reactor module or Gradle subproject is enforced by the **compiler**, not by
convention: a dependency the module graph does not declare cannot compile, no matter
what anyone imports. Where a violated boundary matters enough to defend permanently,
"promote this package to a module" is a stronger recommendation than any lint rule —
and it is a recommendation Java can make that Python and TypeScript cannot.

JPMS (`module-info.java`) is stronger again, at the cost of fighting Spring Boot's fat
jar and most of the agent-based ecosystem. Mention it only where the project already
uses it; proposing JPMS adoption to a Spring Boot application is usually wrong.

## Abstractness (appendix) — exact here, unlike Python

`A = abstract types / total types` per component. Java is the language Martin defined
these metrics for, and the count is **unambiguous**: interfaces and `abstract` classes
are abstract, everything else is concrete, with no `Protocol`-shaped hole to
under-count. So `A`, and therefore `D = |A + I − 1|`, are exact rather than
approximate — say so in the report, since the other language references cannot.

One judgement call: `sealed` interfaces and `record` implementations. A sealed interface
is abstract by every structural definition; count it as such, and note that a component
modelling a closed domain union will legitimately sit high on `A` without that being
abstraction for its own sake.

Emit the Main-Sequence table only under `--metrics`.

## Screaming Architecture and the composition root — the Spring wrinkle

Spring's component scanning means **the composition root is implicit and scattered**:
there is no one place that says how the application is assembled, only annotations
distributed across the classes being assembled. Two findings follow, and both are
Spring-specific enough to miss if you carry over the Python heuristics:

- A top-level package tree of `controller/`, `service/`, `repository/`, `entity/`
  screams *Spring*, not the business. That is the canonical Screaming Architecture
  finding in this ecosystem and it is near-universal in generated or tutorial-shaped
  codebases.
- `@Configuration` classes **are** the composition root wherever explicit `@Bean`
  methods exist. Where everything is `@Component` + scanning, the honest report is that
  the project has no composition root — which is a finding, not a gap in the audit.

## Degrade path (no graph tool)

Only reachable if the project will not compile. Scan `import` statements to build a
rough type→imports map, identify the core/detail split from package names and framework
imports, and reason about cycles and stability qualitatively. Java imports are far more
reliable than Python's — no conditional or runtime import to speak of — but they miss
fully-qualified inline references and every container-mediated edge. State the
limitation; the Dependency-Rule and Screaming-Architecture findings survive, only exact
cycle enumeration and the `I`/`A` numbers are weaker.
