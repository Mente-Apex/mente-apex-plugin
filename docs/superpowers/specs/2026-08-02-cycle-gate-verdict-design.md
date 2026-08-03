# The cycle-gate verdict — design

**Status: PARTIALLY IMPLEMENTED 2026-08-03.** Plan:
[`../plans/2026-08-02-cycle-gate.md`](../plans/2026-08-02-cycle-gate.md).

A spec marked implemented is read as a description of the code, so the three
gaps are named here rather than left for a reader to discover:

| Gap | Section | Status |
|---|---|---|
| `TierMap` | §4.1 | **Not built, in any form.** Nothing decides which probes are affordable at which frequency; `lizard` is simply always run. |
| The advisory in the verdict | §4.5, §5 | **Not wired.** `scripts/complexity_probe_advisory.py` exists and is tested, but has no production caller, so no `unverified` reason carries install coordinates. The only implemented probe is `lizard`, which §4.5's own table excludes — the advisory waits on the first bytecode-reading probe. |
| `NullThresholds` as the default source | §4.1 | **Vestigial.** The class exists but is not in `default_threshold_sources()`; `discover_thresholds` returns the `NO_THRESHOLDS` constant when every source declines, which is the same honest answer by a different route. |

Everything else in §4 ships: `ComplexityProbe`/`LizardProbe`, the four
`ThresholdSource` implementations, all three `MeasurementSink`s, `CycleGate`,
and the status vocabulary invariant. One further deliberate divergence, ruled
by the human rather than pending: `--gate` on this CLI is a **reporter, not a
blocker** (see `scripts/complexity_probe.py`'s module docstring for why the
blocking branch cannot fire from a self-contained entry point).
Resolves §5.1 and §5.2 of
[`2026-07-30-quality-in-the-loop-design.md`](2026-07-30-quality-in-the-loop-design.md),
which were the two open questions blocking [#117](https://github.com/menteapex/mente-apex-plugin/issues/117)
and [#124](https://github.com/menteapex/mente-apex-plugin/issues/124).

Stress-tested against Java 25 / Spring Boot 4, whose bytecode-based tooling
cannot run per-cycle at all — the case that breaks any design assuming every
check is always available.

**Reference convention.** Both documents have a §5.1 and a §5.2. Sections of the
parent are written **"parent §5.1"**; a bare "§4.2" always means this document.

---

## 1. The question, and why it was stuck

Parent §5.1 asked what the cycle-gate does when a check breaches, and offered three
options: **block** (fires on legitimate code, trains reflexive override),
**warn** (prose with extra steps — the exact failure being fixed), **annotate**
(weaker per-edit, but survives). Each has a real flaw, which is why it sat open.

All three share an assumption: **that the gate passes judgment on the code.**
That assumption is what was stuck, not the choice between them.

### 1.1 Which failure mode is real

The gate exists to fix one observed problem, named by the skill itself
(`skills/tdd/SKILL.md:158-159`):

> *"Evaluate every cycle, even when the outcome is 'nothing to refactor' — say so
> explicitly. **Silence is how this step evaporates.**"*

The failure is **silent skipping** — the REFACTOR step producing nothing at all.

The rival hypothesis, *rationalized breaches* (the agent sees CC 24 and talks
itself past it), has never been observed and **could not have been**: nothing in
the toolkit computes cyclomatic complexity, so there has never been a number to
rationalize past. It is a hypothetical failure mode of a system that does not
yet exist. Design for the observed one.

---

## 2. The ruling

> **The gate does not return a verdict on the code. It returns a verdict on
> whether the check ran.**

Two consequences, both of which dissolve parent §5.1's deadlock:

- **A function at CC 24 is still "a place to look, never a finding."** Parent §3.1's
  governing ruling survives contact with the gate completely intact. It was
  never in danger, because the gate does not rule on that.
- **A REFACTOR step that produced no measurement is the breach.** Binary,
  mechanical, unarguable.

### 2.1 Why blocking is now safe

Parent §5.1's objection to blocking was that *"a CC>15 block will fire on legitimate
code and train you to reflexively override, which destroys the signal."*

Correct — for a block on **content**. A block on **process** ("you did not
measure") is never wrong. There is no legitimate reason to skip the step, so it
never fires on good work, so it never trains an override reflex. The objection
does not transfer.

**Enforce that the check ran. Never enforce what it found.**

### 2.2 The verdict vocabulary is #121's, unchanged

The gate's verdict vocabulary and the report status vocabulary
([#121](https://github.com/menteapex/mente-apex-plugin/issues/121)) turn out to
be one mechanism seen twice:

| Verdict | Meaning | Blocks? |
|---|---|---|
| `ran` | measurement produced, numbers in the transcript | no |
| `degraded` | some files measured, some not (polyglot repo, partial run, time budget hit) | no |
| `unverified` **with a stated reason** | could not run — no probe for the language, tool absent, needs compiled classes | no |
| **silence** | a probe was available and nothing was said | **yes** |

### 2.3 The gate in one sentence

> **Produce a measurement, or state why there isn't one. Silence is the only
> thing that blocks.**

This is the formulation to implement against. It maps exactly onto the diagnosed
failure, cannot fire wrongly, and works on a language with zero tooling
available.

### 2.4 The bug this fixes

An earlier draft of this design blocked on "no measurement present". That
**bricks any language the probe cannot parse** — the agent would be permanently
unable to satisfy a gate that can never be satisfied. It would also stop every
Java cycle forever, since Java's structural tools cannot run at cycle frequency.

Distinguishing *could not* (`unverified` + reason, non-blocking) from *did not*
(silence, blocking) is therefore load-bearing, not a nicety.

---

## 3. Scope: gates are for agent-written code

**Humans get feedback. Agents get gates.**

This was implicit in an earlier draft and caused a scope error worth recording:
everything hung off the TDD cycle's REFACTOR step, which only exists when the
agent is driving. Hand-written code — e.g. learning Java by writing it — was
served by nothing.

A hard constraint makes this unfixable by hooks alone: **Claude Code hooks fire
only on Claude's own tool calls.** Code typed into an IDE is structurally
invisible to any hook this plugin ships. Live feedback on hand-written code
belongs to the IDE (SonarLint, Checkstyle) — which is also, conveniently, the
same config §4.2's threshold discovery reads.

| | Agent writes it | Human writes it |
|---|---|---|
| Risk | skips the check silently | still learning the idiom |
| Response | **blocked** until it measures | numbers on request, **never blocking** |
| Trigger | the TDD cycle | explicit invocation |

This scope split **confirms** the §2 ruling rather than denting it. Blocking on
"you did not measure" is aimed at the agent and is inert for a human. Had the
design instead picked the obvious-looking "block when CC > 15", it would have
fired on a learner's hand-written Java — actively hostile to the use case.

---

## 4. Design

### 4.1 Components and their single responsibilities

| Unit | One reason to change |
|---|---|
| `ComplexityProbe` | how a language's source is measured |
| `ThresholdSource` | where a project's declared limits are read from |
| `MeasurementSink` | where a measurement is delivered |
| `TierMap` | which probes are affordable at which frequency |
| `ToolAdvisory` | what a build system needs to make a missing tool available |
| `CycleGate` | deciding `ran` / `degraded` / `unverified` / silence |

**`ComplexityProbe`** — `measure(paths) -> Measurement`. `LizardProbe` is the
only implementation today. Callers depend on the protocol; nothing outside the
implementation knows lizard exists.

**`ThresholdSource`** — `thresholds_for(language) -> Thresholds | None`.
Implementations read what the target repo already declares: `CheckstyleThresholds`,
`PmdThresholds`, `RuffThresholds` (`mccabe` / `C901`), `EslintThresholds`
(`complexity`), and `NullThresholds` as the honest default. Adding a language is
adding a file, never editing a working implementation — the existing
detect-and-load convention (`docs/refactor-workflow.md:110-128`).

**`MeasurementSink`** — one producer, three consumers:

| Sink | Consumer | Behavior |
|---|---|---|
| `TranscriptSink` | the TDD cycle | numbers into the transcript; gate enforces |
| `ArtifactSink` | Phase 0 audit (#117 → #118) | the shared Measurements artifact |
| `ReviewSink` | on-demand chunk review | numbers, then hand to a judgment lens |

This is §4 of the parent spec ("#117 has two consumers — build once, feed both")
with a third consumer added. The producer does not know which sink it feeds.

**`TierMap`** — injected data, not logic: which probes are affordable at which
rung, per language. Java's entry places `lizard` at cycle frequency and
`jdeps` / ArchUnit / PIT at branch frequency.

**`ToolAdvisory`** — see §4.5.

**`CycleGate`** — holds only the §2.3 rule. Receives a probe, a sink, a tier map
and an advisory; owns no knowledge of any concrete tool.

### 4.2 Thresholds (resolves parent §5.2)

Parent §5.2 asked who sets thresholds and where, and worried that an unconfigured
project has no gate. **Under §2 the question is off the critical path** — the
gate blocks on silence, not on breach, so a project with no thresholds still has
a fully functioning gate. Numbers remain triage inputs, exactly as parent §3.1 rules.

Where thresholds *do* exist, defer to what the repo already declares
(Checkstyle / PMD / Sonar, ruff `mccabe`, ESLint `complexity`). Where it declares
none, report the distribution and assert nothing.

**The plugin ships no default numbers.** This upholds
`docs/clean-code-standard.md:41-48` ("Prefer 'can I read this in one pass?' over
'how few lines per function?'") rather than quietly contradicting it.

This also mirrors a pattern the plugin already uses — `clean-architecture/references/java.md`
reads existing ArchUnit rules before proposing its own.

### 4.3 Chunk review (the human path)

Reuses skills that already accept a chunk. Feeding them a `Measurement` adds
triage to judgment without touching their judgment logic — open/closed.

**Verified against the skills, 2026-08-02** — the reuse holds, but two of the
three chunk forms below are new work, not existing capability:

| Skill | Documented today | Source |
|---|---|---|
| `/clean-code` | `/clean-code [scope]`, reviews *"a diff, file, or PR"*; gears scale to scope size | `skills/clean-code/SKILL.md:7,35,42-45` |
| `/solid` | `/solid [path]` — *"`path` scopes the analysis (default: repo root)"* | `skills/solid/SKILL.md:38` |

A chunk is, in order of expected use:

| Form | Example | Status |
|---|---|---|
| **unspecified** — everything uncommitted in the working tree | `/clean-code` | **new** — `/solid` currently defaults to *repo root*, and `/clean-code` states no bare default |
| **a path** — that file or directory | `/clean-code src/main/java/orders/` | **exists** in both |
| **a range** — one method | `/clean-code OrderService.java:40-120` | **new** — neither skill documents line ranges |

The working-tree default matters more than it looks: a learner asking *"check
what I just wrote"* does not want `/solid`'s whole-repo audit. Repo root is the
right default for an audit and the wrong one for a chunk, so the chunk path must
supply its own.

The number triages; the lens judges. For a learner the lens output is the
valuable half — *"this is a type switch; Java 25's sealed interfaces plus
pattern-matching switch are built for it, and the compiler then catches a
missing branch"* — and the language references carrying that knowledge already
exist in `solid/`, `gof/`, `ddd/`, `clean-architecture/`, `tdd/`.

### 4.4 Invocation surface

The contract implementation must satisfy. Three entry points, matching the three
sinks — and **no new skill**, per §8.

**1. Automatic, during a TDD cycle** (agent-written code). Nothing to type. The
REFACTOR step calls the probe and reports; the gate enforces §2.3. This is the
only path that can block.

**2. Explicit, on a chunk** (hand-written code). Existing skills, now
measurement-backed:

```
/clean-code                            # everything uncommitted in the working tree
/clean-code OrderService.java          # one file
/clean-code src/main/java/orders/      # a directory
/clean-code OrderService.java:40-120   # one method you're unsure about
/solid <same chunk forms>              # same, through the SOLID lens
```

Never blocks. Prints the numbers, then the lens judges what the numbers point
at. This is the path for learning a language by writing it.

**3. Numbers only, no judgment** — the probe run directly, following the
convention `scripts/mutation_gate.py` already sets:

```
scripts/complexity_probe.py <paths>          # measure and print
scripts/complexity_probe.py --scope working-tree
scripts/complexity_probe.py --json           # for a sink to consume
```

`--scope` takes the same values the mutation gate does (`merge-base`,
`working-tree`, `full`) so the two sensors share one vocabulary.

**Two of these forms do not exist yet** — the bare working-tree default and the
line range (§4.3). They are requirements on the implementation, not descriptions
of current behavior.

**Documentation duty at implementation time.** `README.md` and the affected
`SKILL.md` files (`tdd`, `clean-code`, `solid`, `code-quality`) must be updated
in the same change that ships the behavior — not before, since documenting an
uninvokable command is worse than documenting nothing. The plugin's standing
rule ("always update README.md when changing the plugin — skills, commands,
scripts, structure") applies.

### 4.5 Tool advisories — making `unverified` actionable

An `unverified` verdict says *why* a check could not run. On its own that is a
dead end: "PIT is not in the build" leaves the reader to go find out what to do
about it. The verdict should also say **how to make the tool available**.

This is a distinct reason to change — build coordinates and plugin ids move
independently of probe logic — so it is a separate unit, not a field the probe
fills in.

**`ToolAdvisory`** — `advice_for(tool, build_system) -> Advice | None`.
Implementations: `GradleKotlinAdvisory`, `GradleGroovyAdvisory`,
`MavenAdvisory`, `NullAdvisory`. The build system is detected from the repo
(`build.gradle.kts` / `build.gradle` / `pom.xml`); an unrecognized one yields
`NullAdvisory` and the verdict simply carries no advice. Adding a build system
is adding a file.

**Advice is offered, never enforced.** A missing tool remains `unverified` and
remains non-blocking (§3). The advisory does not turn into a nag, is printed
once per verdict, and never converts absence into a finding.

#### What to add, per tool (JVM)

Coordinates are stable; **versions are not** — pin the current release rather
than copying a number from this table.

| Tool | Gradle (Kotlin DSL) | Maven |
|---|---|---|
| **ArchUnit** — dependency rules as a JUnit test | `testImplementation("com.tngtech.archunit:archunit-junit5:<version>")` | `com.tngtech.archunit:archunit-junit5`, scope `test` |
| **PIT** — mutation testing | `id("info.solidsoft.pitest")` plugin + `testImplementation("org.pitest:pitest-junit5-plugin:<version>")` | `org.pitest:pitest-maven` plugin + `org.pitest:pitest-junit5-plugin` dependency |
| **JaCoCo** — coverage | built-in: `plugins { jacoco }` | `org.jacoco:jacoco-maven-plugin` |
| **Checkstyle** — declared complexity limits | built-in: `plugins { checkstyle }` | `org.apache.maven.plugins:maven-checkstyle-plugin` |
| **PMD** — declared complexity limits | built-in: `plugins { pmd }` | `org.apache.maven.plugins:maven-pmd-plugin` |
| **SpotBugs** | `id("com.github.spotbugs")` | `com.github.spotbugs:spotbugs-maven-plugin` |
| **Spring Modulith** — module boundary verification | `testImplementation("org.springframework.modulith:spring-modulith-starter-test")` — version managed by the Boot 4 BOM | same, via the Boot 4 BOM |
| **jdeps** | none — ships with the JDK | none |
| **lizard** — the complexity probe | none — a Python tool, resolved via `uv run --with lizard`, never a build dependency | none |

#### Java 25 caveat the advisory must carry

**Every bytecode-reading tool above must be new enough to parse class-file
version 69 (Java 25).** ArchUnit, PIT, JaCoCo and SpotBugs all read compiled
classes and historically lag a new JDK release by weeks to months. A version
that is merely "recent" is not sufficient.

The advisory must state this constraint rather than name a version, because a
version number written into a spec goes stale silently and would be copied into
a build where it fails with an opaque class-file error. When a tool is present
but fails on class-file version, that is `unverified` with the reason *"tool
predates Java 25 class files"* — distinct from *"tool absent"*, and pointing at
an upgrade rather than an install.

`jdeps` and `lizard` are exempt: `jdeps` ships with the JDK in use, and `lizard`
reads source text (§5.2 verifies it on Java 25 syntax).

### 4.6 How DIP shaped this

High-level policy (`CycleGate`, the REFACTOR step, the review lenses) depends
only on the four protocols above. Every collaborator is constructor- or
parameter-injected; nothing constructs a concrete probe, sink, or threshold
reader in place. There are no globals and no singletons.

The payoff is concrete and immediate: **all verdict logic is testable with a
stub probe and no subprocess** (§6). ISP is honored by five narrow protocols
rather than one `QualityGate` interface that every consumer would over-import.

`ToolAdvisory` is the clearest case of the split earning its keep: build
coordinates and JDK-compatibility floors change on someone else's release
schedule, and none of that reaches the probe, the sink, or the gate.

---

## 5. Failure handling

Every row is non-blocking. Where a build could supply the missing tool, the
verdict also carries the §4.5 advisory.

| Case | Outcome | Advice? |
|---|---|---|
| Probe unavailable for the language | `unverified` + reason | no — nothing to add |
| lizard not installed | `unverified` + reason. Rare: `uv run --with lizard` resolved it in ~20ms under test. | no — not a build dependency |
| Tool absent from the build (ArchUnit, PIT, JaCoCo, Checkstyle, PMD) | `unverified — <tool> not in the build` | **yes** — coordinates for the detected build system |
| Tool present but predates Java 25 class files | `unverified — <tool> cannot read class-file 69` | **yes** — upgrade, not install |
| Java structural tools at cycle tier | `unverified — needs compiled classes, deferred to branch tier`. Self-documents the tier map. | no — it is present, just not affordable here |
| Probe exceeds its time budget | partial result, `degraded`, state what was skipped | no |
| Chunk too large for the tier | cycle measures changed functions only; review measures what it is pointed at; audit measures everything | no |

Note the third and fourth rows are deliberately different verdicts. *Absent* and
*too old* point at different fixes, and collapsing them would send a reader to
add a dependency that is already there.

### 5.1 Known probe inaccuracy

lizard 1.23.0 **misses `when` guards** on Java pattern-matching switches. A
switch with five arms and two guards scored CC 6 where 8 is correct.

Harmless by construction: numbers never decide a verdict, so an undercount
cannot cause a wrong block. Recorded because it will otherwise be rediscovered
as a bug.

### 5.2 Java 25 probe verification (empirical, 2026-08-02)

lizard 1.23.0 parses Java 25 without error:

| Construct | Result |
|---|---|
| `sealed interface` + `record` implementations | parsed; no phantom functions |
| pattern-matching `switch` with `when` guards | parsed; CC undercounts guards (§5.1) |
| compact source file — `void main()`, `import module java.base` (JEP 511/512) | parsed, CC 7 |
| flexible constructor bodies (JEP 513) | parsed, CC 4 |

Settles the open verification item: **lizard is a viable Java 25 probe.**

---

## 6. Testing

Three groups, in descending order of importance:

1. **Verdict logic, stub probe, no subprocess.** Silence blocks; `unverified`
   with a reason does not; `ran` does not; `degraded` does not. Pure logic, and
   the tests that actually protect the design.
2. **Real-probe fixtures**, one small file per language, committed. The Java 25
   fixtures from §5.2 go in as-is — they are the regression net for "can the
   probe still parse this language."
3. **Threshold discovery** against fixture repos containing a `checkstyle.xml`,
   a ruff config, an `.eslintrc`, and one containing nothing — the last must
   yield no thresholds rather than invented ones.
4. **Advisories** — a Gradle-Kotlin, a Gradle-Groovy and a Maven fixture each
   yield build-appropriate coordinates for the same missing tool; an
   unrecognized build system yields no advice rather than a guess; *absent* and
   *predates-Java-25* yield different advice (§5).

The mutation gate should cover the verdict logic: branching on
ran/degraded/unverified/silence is exactly where a vacuous test hides.

---

## 7. What this unblocks

| Issue | Status after this spec |
|---|---|
| [#117](https://github.com/menteapex/mente-apex-plugin/issues/117) | unblocked — probe + sinks are its implementation |
| [#124](https://github.com/menteapex/mente-apex-plugin/issues/124) | unblocked — proposal 1 (REFACTOR calls a script) is the build; proposal 2 (PostToolUse hook) is not needed for the diagnosed failure |
| [#121](https://github.com/menteapex/mente-apex-plugin/issues/121) | merged into this — same vocabulary, two surfaces |
| [#118](https://github.com/menteapex/mente-apex-plugin/issues/118) | unblocked — `ArtifactSink` is its input |

Still open in the parent spec, untouched here: parent §5.3 (QA procedures), parent §5.4 (does
the umbrella shrink), parent §5.5 (#122's two calls), parent §5.6 (what counts as a domain),
and all of §6 (a gauntlet that learns).

---

## 8. Explicitly not doing

- **A git pre-commit hook.** Would catch hand-written work automatically, but on
  a human it either blocks (wrong response, per §3) or is ignorable noise. The
  requirement was explicit invocation. Revisit only if the need appears in use.
- **Default thresholds shipped by the plugin.** See §4.2.
- **A PostToolUse hook.** Not required by the diagnosed failure mode; revisit
  only if rationalized breaches are ever actually observed.
- **A new skill for chunk review.** `/clean-code` and `/solid` already take a
  chunk; they need numbers, not a sibling.
