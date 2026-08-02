---
technology: java
toolchain: gradle
fingerprint:
  - build.gradle.kts
  - build.gradle
version_source: gradle.properties#version
relock_command: null
gate_command: ./gradlew --no-daemon clean build
build_command: ./gradlew --no-daemon -x test assemble
artifact_pattern: build/libs/*-<version>.jar
tag_pattern: v<version>
publish_command: ./gradlew --no-daemon publish && git push <remote> <default> --follow-tags
install_verify_command: ./gradlew --no-daemon --quiet dependencyInsight --configuration runtimeClasspath --dependency <version>
distribution_names: null
status: stub
---

# java / gradle  (STUB)

Sketched, never exercised — see the contract's `status: stub` section. A **generic**
Gradle component, deliberately: the fingerprint claims every Gradle project, so the
commands must be the ones every Gradle project expects. A repository that ships a
container image resolves `distributions/oci-image.md` alongside this, and that adapter's
`publish_command` replaces the one above.

## `gradle.properties` is the only version this contract can address

`build.gradle.kts` is imperative Kotlin and `build.gradle` imperative Groovy. A line
reading `version = computeVersion()` is not a value any selector language can name — not
because the contract lacks a Gradle row, but because there is nothing there to point at.
This is a real difference from every other toolchain in this skill, and it is why the
contract grew a `.properties` selector row.

The practical consequence for a project adopting this adapter: **the version must live in
`gradle.properties`** as a plain `version=1.2.3`, which Gradle reads into the project
version automatically. A project computing its version in code cannot use this adapter,
and the honest outcome is that detection resolves it and the version read then fails — a
refusal, not a wrong stamp.

`gradle.properties` is **build evidence and not a shared manifest**. An earlier revision
tried to admit it as a fourth shared manifest so a distribution adapter could read an
image name from it; the contract now records why that was rejected, and no distribution
adapter may read it at any selector.

## Fingerprint is the build script, not `gradle.properties`

Detection matches `build.gradle.kts` or `build.gradle` because those are what make a
directory a Gradle component. `gradle.properties` is neither necessary (a Gradle build
runs fine without one) nor sufficient (it appears in repositories that only set
`org.gradle.jvmargs`), so fingerprinting it would both miss real Gradle projects and
claim ones that are not releasable this way.

The two entries are **alternatives, not a precedence** — the contract is explicit that a
fingerprint list is an OR where any match selects the same adapter, and both entries here
resolve the same commands. Listing `.kts` first is presentation, and reading anything more
into it would invent an ordering the contract denies.

The `version_source` file is therefore **not** the fingerprint file, which is the case the
contract's "a fingerprint match is not a fit" rule exists for: a Gradle project with no
`gradle.properties` matches this adapter and then refuses at the version read.

## `artifact_pattern` globs where Maven names

Maven names its artifact exactly because `artifactId` is a declared, addressable field.
Gradle's archive base name defaults to `rootProject.name` in `settings.gradle.kts`, which
is imperative and unaddressable, so there is no role to declare and the pattern globs on
the version instead. `distribution_names` is `null` for the same reason: nothing this
adapter runs can name the built thing, and the contract requires a `null` map to be a
positive claim rather than an omission — this is that claim.

The glob is genuinely weaker than Maven's. `assemble` on a Spring Boot project produces
both the executable boot jar and, when the plain `jar` task is enabled, a second archive
with a `-plain` classifier — and both match. A project in that shape should tighten this
pattern, or disable the plain jar.

## `--no-daemon`, and why it is not an optimisation

The Gradle daemon persists between invocations and caches build state. In a release that
is a liability rather than a speed-up: the gate's `clean build` is meant to prove the
project builds from nothing, and a warm daemon can satisfy it from state a fresh checkout
would not have. `--no-daemon` makes the gate mean what it says.

This cuts the opposite way from the inner-loop advice in
`tdd/references/java-junit5.md`, which leans on Gradle's up-to-date checks and build
cache. Both are correct for their context: caching is what makes the red-green loop
usable and what makes a release gate a lie.

## `relock_command: null` — conditional, unlike Maven's

Maven's `null` is unconditional: there is no lockfile to go stale. Gradle's is a claim
about **this** project. Gradle does have dependency locking — it is opt-in, and a project
that has enabled it commits `gradle.lockfile` (or `gradle/dependency-locks/`). Those lock
**dependency** versions, not the project's own, so stamping `version` in
`gradle.properties` still cannot invalidate them and `null` remains correct.

The case that would break it: a project whose own version appears inside a lockfile
because it locks a dependency on a sibling module of itself. If that is your repository,
declare `./gradlew dependencies --write-locks` here — and note the contract's warning that
a relock must be *narrow*, since that command also picks up upstream dependency drift and
sweeps it into the release commit unreviewed.

## Still unverified

Everything, and `install_verify_command` most of all. Gradle has no `dependency:get`
equivalent — no single command that proves a published coordinate is resolvable from a
clean state — and the `dependencyInsight` invocation above is a **guess that has never
been run**. It very likely reports on the project's own dependency graph rather than on
the artifact just published, which would make it a check that passes regardless. Treat
this field as the one to resolve first when exercising the adapter; the honest alternative
is a scratch `settings.gradle.kts` that declares the published coordinate and resolves it.

Also unverified:

- whether `publish` alone is right, or whether the project needs `publishToMavenLocal` /
  a named publication task;
- whether `-x test` on `assemble` is meaningful (the task may not depend on `test`,
  making the exclusion harmless but misleading);
- whether the `artifact_pattern` glob survives a project using version classifiers.
