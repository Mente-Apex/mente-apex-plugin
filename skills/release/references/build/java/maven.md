---
technology: java
toolchain: maven
fingerprint: pom.xml
version_source: pom.xml#/project/version
relock_command: null
gate_command: ./mvnw -B clean verify
build_command: ./mvnw -B -DskipTests package
artifact_pattern: target/<distribution-name:artifact>-<version>.jar
tag_pattern: v<version>
publish_command: ./mvnw -B -DskipTests spring-boot:build-image -Dspring-boot.build-image.publish=true && git push <remote> <default> --follow-tags
install_verify_command: jar tf target/<distribution-name:artifact>-<version>.jar | grep -q '^BOOT-INF/'
distribution_names:
  group: pom.xml#/project/groupId
  artifact: pom.xml#/project/artifactId
  image: pom.xml#/project/properties/spring-boot.build-image.imageName
status: stub
---

# java / maven

**Still `status: stub`, and deliberately so.** The five open questions the previous
draft listed are now resolved below — this adapter is no longer sketchy — but resolving
them on paper is not the exit condition. The contract's `status: stub` section is
explicit: the marker means *"sketched, never exercised"*, and it clears by **running
every command against a real repository**, not by arguing about them. Nothing here has
been run. Cutting the first Spring Boot release with this adapter is the exercise;
expect to correct something.

## Scope: this adapter releases a deployable, not a library

It builds a Spring Boot application and publishes an **OCI image**. That single choice
settles four of the fields below, and it is why several of them disagree with what a
Maven adapter would look like if the artifact were a library going to Maven Central.
A library needs a different adapter — `publish_command`, `install_verify_command` and
`tag_pattern` all change — not an edit to this one.

## The five resolved questions

**Group and artifact are two roles, and `groupId` is frequently inherited.** The `:`
joining them lives in a command (`maven-central.md`'s `dependency:get`), where it is
Maven's syntax, never inside a selector value where it would be the contract's.
`/project/groupId` is **absent from a child POM that inherits it** from
`/project/parent/groupId`, so this adapter is correct only for a POM that declares its
own. A multi-module reactor needs the group read from the parent, which is a different
selector and therefore a different adapter.

**The version literal, and why this adapter is single-module only.** `pom.xml` carries
both `/project/version` and `/project/parent/version`, and a reactor repeats the version
in every child. The core's single-literal check finds those and refuses — correctly.
This adapter therefore declares the **single-module** shape, where `/project/version` is
the only literal in the tree and the check passes cleanly. That covers the ordinary
Spring Boot application.

A reactor build has two ways out, and both are somebody else's adapter:

- **`${revision}` plus `flatten-maven-plugin`** — the version literal lives once, in
  `/project/properties/revision`, and every POM interpolates it. This fits the contract
  *better* than the single-module shape, and it is the sibling adapter to write next.
  Its Level 2 fingerprint distinguishes itself cleanly with the predicate form:
  `pom.xml#/project/version==${revision}`, positioned **above** this adapter's row so
  the narrower shape wins.
- **Listing every child POM in `derived_manifests`** — legal but brittle: a module added
  later is a version literal nothing stamps, and the failure lands mid-release.

**The tag is `v<version>`, and the previous draft's reasoning no longer applies.** That
draft used `<artifactId>-<version>` because `maven-release-plugin` tags that way by
default. This adapter never invokes `maven-release-plugin` — the release mechanism is an
image push — so its tag convention has no claim here, and `v<version>` is what the git
tooling, the changelog and every other adapter in this skill expect. **The general
lesson survives the change**: `tag_pattern` is per-target because the *release
mechanism* dictates it, which is exactly why it cannot be a constant. A project that
does drive releases through `maven-release-plugin` needs the other pattern, and that is
another adapter.

**`mvn versions:set` is the wrong stamp mechanism here.** It rewrites the version across
a reactor, which is precisely the multi-module behavior this adapter has excluded, and
it emits `.versionsBackup` files the core would then have to know to clean up. For a
single-module POM the core's ordinary file rewrite of `/project/version` is both
sufficient and less surprising. Revisit this in the `${revision}` sibling, where the
stamp target is a property rather than the version element.

**`relock_command: null` is a claim, not a gap.** Maven resolves dependencies at build
time and commits no lockfile, so stamping the POM cannot make anything in the tree
stale. A project that has adopted a third-party lock plugin has left that assumption
behind and must declare its refresh command here.

## The Spring Boot repackaging trap

`spring-boot-maven-plugin` **repackages** the jar during `package`: the executable fat
jar takes the original name, and the plain jar produced by `maven-jar-plugin` is moved
aside to `<artifactId>-<version>.jar.original`. So the obvious glob
`target/*-<version>.jar` is satisfied by whichever of the two exists — it cannot tell
you which one you got, and it matches even when repackaging silently did not run.

Two fields defend against this. `artifact_pattern` names the artifact exactly via the
`artifact` role rather than globbing, so the verified path is the deployable one. And
`install_verify_command` greps the archive for a `BOOT-INF/` entry, which exists **only**
in a repackaged boot jar: a plain jar passes `jar tf` perfectly well and fails this
check, which is the whole point. Verifying the built thing "installs" means, for an
application, that it is actually the runnable artifact and not the library jar wearing
its name.

## `clean verify`, not `clean test`

`verify` runs the failsafe integration tests and the full packaging lifecycle, which is
what a release gate should do. Do not weaken it to `test` — that skips every `*IT` class,
and integration tests are where a Spring wiring break actually surfaces.

## Everything runs through `./mvnw`

The wrapper pins the Maven version the way a lockfile pins dependencies. A release built
with an ambient `mvn` is a release built with whatever the operator's shell resolved,
which is the class of irreproducibility this skill exists to prevent. A repository with
no `mvnw` should get one (`mvn wrapper:wrapper`) before it releases.

## Still unverified

Everything, in the sense that matters — nothing below has been run:

- whether `spring-boot:build-image` with `publish=true` authenticates from the ambient
  Docker credential helper or needs explicit `<docker><publishRegistry>` configuration
  in the POM (it likely needs the latter, and if so this `publish_command` is incomplete);
- whether `-DskipTests` on `build-image` is honoured, or whether the plugin re-runs the
  lifecycle anyway;
- whether `jar` and `grep` are the right reachability check on a machine where only the
  JDK is guaranteed present;
- the interaction between `build_command` and `publish_command` both producing artifacts,
  and whether the image build reuses the jar `package` already produced.
