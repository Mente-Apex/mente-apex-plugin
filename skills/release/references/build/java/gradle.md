---
technology: java
toolchain: gradle
fingerprint:
  - build.gradle.kts
  - build.gradle
version_source: gradle.properties#version
relock_command: null
gate_command: ./gradlew --no-daemon clean build
build_command: ./gradlew --no-daemon -x test bootJar
artifact_pattern: build/libs/*-<version>.jar
tag_pattern: v<version>
publish_command: ./gradlew --no-daemon bootBuildImage --publishImage && git push <remote> <default> --follow-tags
install_verify_command: jar tf build/libs/*-<version>.jar | grep -q '^BOOT-INF/'
distribution_names:
  image: gradle.properties#imageName
status: stub
---

# java / gradle

Sketched, never exercised — see the contract's `status: stub` section. Like its Maven
sibling this adapter releases a **deployable Spring Boot application as an OCI image**,
not a library.

## `gradle.properties` is the only version this contract can address

`build.gradle.kts` is imperative Kotlin and `build.gradle` imperative Groovy. A line
reading `version = computeVersion()` is not a value any selector language can name — not
because the contract lacks a Gradle row, but because there is nothing there to point at.
This is a real difference from every other toolchain in this skill, and it is why the
contract grew a `.properties` selector row and admitted `gradle.properties` as its
fourth shared manifest; the argument is recorded there rather than here.

The practical consequence for a project adopting this adapter: **the version must live
in `gradle.properties`** as a plain `version=1.2.3`, with the build script reading it
implicitly (Gradle does this automatically for the `version` property) rather than
assigning one. A project computing its version in code cannot use this adapter, and the
honest outcome is that detection resolves it and the version read fails — a refusal, not
a wrong stamp.

## Fingerprint is the build script, not `gradle.properties`

Detection matches `build.gradle.kts` or `build.gradle` because those are what make a
directory a Gradle component. `gradle.properties` is neither necessary (a Gradle build
runs fine without one) nor sufficient (it appears in repositories that only set
`org.gradle.jvmargs`), so fingerprinting it would both miss real Gradle projects and
claim ones that are not releasable this way. The Kotlin DSL is listed first because a
project carrying both is mid-migration and the `.kts` file is the live one.

The `version_source` file is therefore **not** the fingerprint file, which is the case
the contract's "a fingerprint match is not a fit" rule exists for: a Gradle project with
no `gradle.properties` matches this adapter and then refuses at the version read, which
is the designed behavior rather than a gap.

## `artifact_pattern` globs where Maven names

Maven can name its artifact exactly because `artifactId` is a declared, addressable
field. Gradle's equivalent — the archive base name — defaults to `rootProject.name` in
`settings.gradle.kts`, which is imperative and unaddressable, so there is no role to
declare and the pattern globs on the version instead. That is weaker: it would match two
jars if the build produced two.

It usually does not, because `build_command` runs **`bootJar`** rather than `build`.
Gradle's Spring Boot plugin produces the executable boot jar from `bootJar` and, when
the plain `jar` task is also enabled, a second archive with a `-plain` classifier. Naming
`bootJar` keeps one artifact in `build/libs/`. A project that has re-enabled the plain
jar will match two and should tighten this pattern.

`install_verify_command` carries the same `BOOT-INF/` check as the Maven adapter and for
the same reason: it is the one entry that exists only in a repackaged boot jar, so a
plain jar wearing the right filename fails it.

## `--no-daemon`, and why it is not an optimisation

The Gradle daemon persists between invocations and caches build state. In a release that
is a liability rather than a speed-up: the gate's `clean build` is meant to prove the
project builds from nothing, and a warm daemon can satisfy it from state a fresh checkout
would not have. `--no-daemon` makes the gate mean what it says. The cost is real — every
release pays full JVM startup — and it is the right trade for a step that runs once per
release rather than once per edit.

Note this cuts the opposite way from the inner-loop advice in
`tdd/references/java-junit5.md`, which leans on Gradle's up-to-date checks and build
cache. Both are correct for their context: caching is what makes the red-green loop
usable and what makes a release gate a lie.

## `relock_command: null` — conditional, unlike Maven's

Maven's `null` is unconditional: there is no lockfile to go stale. Gradle's is a claim
about **this** project. Gradle *does* have dependency locking — it is opt-in, and a
project that has enabled it commits `gradle.lockfile` (or `gradle/dependency-locks/`).
Those lock **dependency** versions, not the project's own, so stamping `version` in
`gradle.properties` still cannot invalidate them and `null` remains correct.

The case that would break it: a project whose own version appears inside a lockfile
because it locks a dependency on a sibling module of itself. If that is your repository,
declare `./gradlew dependencies --write-locks` here — and note the contract's warning
that a relock must be *narrow*, since that command will also pick up any upstream
dependency drift and sweep it into the release commit unreviewed.

## Still unverified

- whether `-Ppitest`-style property overrides are needed for `bootBuildImage` registry
  credentials, or whether it reads the ambient Docker config;
- whether `--publishImage` requires `docker.publishRegistry` to be configured in the
  build script, in which case this `publish_command` is incomplete;
- whether `-x test` on `bootJar` is meaningful (the task may not depend on `test` at all,
  making the exclusion harmless but misleading);
- whether the glob in `artifact_pattern` and `install_verify_command` survives a project
  with a version-classifier convention;
- the `imageName` property convention itself, which this adapter **imposes** rather than
  inherits — Gradle defines no standard property for it. A project naming its image any
  other way does not resolve the `oci-image` distribution adapter at all.
