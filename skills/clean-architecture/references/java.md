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
jdeps -verbose:package target/classes        # Gradle: build/classes/java/main
```

**No `-filter:none`.** jdeps' default is `-filter:package`, which suppresses only
*self-package* edges — cross-package edges inside your application are already reported,
and those are the ones this lens is about. `-filter:none` adds `com.example.domain ->
com.example.domain` rows you then have to discard, and it disables `-filter:archive`,
which was not on either. It is not load-bearing; it is noise.

Output is `from -> to` pairs at package granularity; aggregate them to your **component**
level (a component is a sub-package tree, not a single package), drop intra-component
edges, then:

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
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.Architectures.onionArchitecture;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

@AnalyzeClasses(packages = "com.example", importOptions = ImportOption.DoNotIncludeTests.class)
class DependencyRuleTest {

    @ArchTest
    static final ArchRule frameworkIsADetail =
            noClasses().that().resideInAnyPackage("..domain..", "..application..")
                    .should().dependOnClassesThat().resideInAnyPackage(
                            "org.springframework..", "jakarta.persistence..", "com.fasterxml.jackson..")
                    .allowEmptyShould(true);

    @ArchTest
    static final ArchRule dependenciesPointInward =
            onionArchitecture()
                    .domainModels("..domain.model..")
                    .domainServices("..domain.service..")
                    .applicationServices("..application..")
                    .adapter("web", "..adapter.web..")
                    .adapter("persistence", "..adapter.persistence..")
                    .withOptionalLayers(true)
                    .ignoreDependency(
                            resideInAnyPackage("com.example", "com.example.config.."),
                            alwaysTrue());

    @ArchTest
    static final ArchRule noCycles =
            slices().matching("com.example.(*)..").should().beFreeOfCycles();
}
```

Three details that decide whether this **runs** rather than merely reads well:

- **`.withOptionalLayers(true)`** — `optionalLayers` defaults to `false`, so every
  declared layer must contain at least one class or the rule fails with `Layer '<name>'
  is empty`. A project with no `..domain.service..` classes yet fails on day one.
- **The `ignoreDependency` on unassigned packages** — `onionArchitecture()` considers all
  dependencies and treats adapters as accessible by no layer, so a class belonging to
  *no* declared layer (`com.example.Application`, `com.example.config.*`) that touches a
  domain or adapter type is a violation. That is the default Spring Boot layout. Assign
  those packages to a layer, exclude them, or keep them out of the imported set.
- **`.allowEmptyShould(true)` on the `noClasses()` rules** — since ArchUnit 1.0,
  `failOnEmptyShould` defaults to true, so a rule about `..domain..` fails outright
  before that package exists. The onion and slices rules set it internally; the
  hand-written ones do not.

**`onionArchitecture()` is the Onion / Hexagonal / Ports-and-Adapters check** — ArchUnit's
own name for it — and it enforces **inter-layer access direction only**. It does *not*
catch framework leakage: a domain class depending on `org.springframework..` is not a
violation of it, because those targets belong to no layer. It does not subsume the
`frameworkIsADetail` rule above; the two are complementary and you need both.

**On an existing codebase, freeze rather than exempt.** `FreezingArchRule.freeze(rule)`
records today's violations as an accepted baseline and fails only on *new* ones, so a
legacy project can adopt the contract before the refactor rather than after. That is
almost always the right first move; a rule weakened with exclusions to make it pass is a
rule that will never tighten.

**The first run throws unless you enable store creation.** `allowStoreCreation` defaults
to `false`, and the failure message (`Creating new violation store is disabled`) is not
obviously about configuration. Set `freeze.store.default.allowStoreCreation=true` in
`archunit.properties`, or pass
`-Darchunit.freeze.store.default.allowStoreCreation=true` for the baselining run; the
store lands in `archunit_store` and should be committed.

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
under-count. So `A`, and therefore `D`, are exact rather than approximate — say so in the
report, since the other language references cannot.

Name which `D` you are reporting. `D = |A + I − 1| / √2` is the original; `D' = |A + I −
1|` is the normalized form, which the *Clean Architecture* book uses and which is what
the formula above gives. Both are in circulation, they differ by a constant factor, and
a report claiming exactness owes the reader the variant.

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
