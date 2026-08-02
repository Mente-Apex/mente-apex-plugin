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
publish_command: ./mvnw -B -DskipTests deploy && git push <remote> <default> --follow-tags
install_verify_command: ./mvnw -B -q dependency:get -Dartifact=<distribution-name:group>:<distribution-name:artifact>:<version>
distribution_names:
  group: pom.xml#/project/groupId
  artifact: pom.xml#/project/artifactId
status: stub
---

# java / maven  (STUB)

**This adapter has never driven a real release.** `/release` refuses to run against it.
The contract's `status: stub` section is explicit that the marker means *"sketched, never
exercised"* and clears by **running every command against a real repository**, not by
resolving its open questions on paper. The questions below are resolved; the commands are
not exercised.

## Scope: a generic Maven component

This adapter builds a Maven artifact and deploys it to whatever repository the POM's
`distributionManagement` names. It is deliberately **not** Spring-Boot-shaped and not
container-shaped, because its fingerprint is bare `pom.xml` — it claims *every* Maven
component in existence, and an adapter that broad must do the thing every Maven component
expects.

An earlier revision got this wrong in an instructive way: it kept `fingerprint: pom.xml`
while changing `publish_command` to push an OCI image. Every plain Maven library then
resolved it, and would have been tagged, had `mvn deploy` skipped, and been reported as a
successful release. That is the incident shape the separation rule already warns about,
arriving through a different door.

**A repository that ships a container image resolves `distributions/oci-image.md`
alongside this adapter, and that distribution adapter's `publish_command` replaces the
one above.** No narrowing of this fingerprint is needed, and none would have worked:
the fact that distinguishes a deployable from a library is a *shipping* fact, which a
build adapter is forbidden to read.

## The five resolved questions

**Group and artifact are two roles, and `groupId` is frequently inherited.** The `:`
joining them lives in the command, where it is Maven's syntax, never inside a selector
value where it would be the contract's. `/project/groupId` is **absent from a child POM
that inherits it** from `/project/parent/groupId`, so this adapter is correct only for a
POM that declares its own. A multi-module reactor needs the group read from the parent,
which is a different selector and therefore a different adapter.

**The version literal, and why this adapter is single-module only.** `pom.xml` carries
both `/project/version` and `/project/parent/version`, and a reactor repeats the version
in every child. The core's single-literal check finds those and refuses — correctly.
This adapter declares the **single-module** shape, where `/project/version` is the only
literal in the tree.

A reactor build has two ways out, and both are somebody else's adapter:

- **`${revision}` plus `flatten-maven-plugin`** — the version literal lives once, in
  `/project/properties/revision`. This fits the contract *better* than the single-module
  shape and is the sibling adapter to write next. Its Level 2 fingerprint distinguishes
  itself with the predicate form, `pom.xml#/project/version==${revision}`, positioned
  **above** this adapter's row so the narrower shape wins.
- **Listing every child POM in `derived_manifests`** — legal but brittle: a module added
  later is a version literal nothing stamps, and the failure lands mid-release.

**The tag is `v<version>`.** `maven-release-plugin` tags `<artifactId>-<version>` by
default, which is why the contract cites Maven as proof that `tag_pattern` cannot be a
constant. That reasoning is about the *release mechanism*, not the technology: this
adapter drives the release itself rather than delegating to `maven-release-plugin`, so
the plugin's convention has no claim here and `v<version>` — what the changelog and every
other adapter expect — is correct. A project that does release through
`maven-release-plugin` needs the other pattern, and that is another adapter.

**`mvn versions:set` is the wrong stamp mechanism here.** It rewrites the version across
a reactor, which is precisely the multi-module behavior this adapter has excluded, and it
emits `.versionsBackup` files the core would then have to clean up. For a single-module
POM the core's ordinary file rewrite of `/project/version` is sufficient and less
surprising. Revisit in the `${revision}` sibling, where the stamp target is a property.

**`relock_command: null` is a claim, not a gap.** Maven resolves dependencies at build
time and commits no lockfile, so stamping the POM cannot make anything in the tree stale.
A project that has adopted a third-party lock plugin has left that assumption behind and
must declare its refresh command here.

## `artifact_pattern` names the artifact rather than globbing

`target/*-<version>.jar` would also match a shaded, sources, or javadoc jar carrying the
same version, and `artifact_pattern` exists to verify that the build emitted **the** thing
it was supposed to. Naming it through the `artifact` role is exact.

Note what this does *not* do: it carries no information about whether the jar is the one
you meant. In a Spring Boot project `spring-boot-maven-plugin` repackages during
`package` — the executable jar takes the original name and the plain jar is moved aside
to `<artifactId>-<version>.jar.original`, which does **not** match this pattern. So the
pattern is satisfied by whichever jar occupies that path, repackaged or not. Verifying
*which* is `distributions/oci-image.md`'s job, and it does so explicitly.

## `clean verify`, not `clean test`

`verify` runs the failsafe integration tests and the full packaging lifecycle, which is
what a release gate should do. Do not weaken it to `test` — that skips every `*IT` class,
and integration tests are where a Spring wiring break actually surfaces.

## Everything runs through `./mvnw`

The wrapper pins the Maven version the way a lockfile pins dependencies. A release built
with an ambient `mvn` is a release built with whatever the operator's shell resolved. A
repository with no `mvnw` should get one (`mvn wrapper:wrapper`) before it releases —
and note that this adapter's fingerprint does **not** check for the wrapper, so a
wrapper-less repo resolves cleanly and then fails at the gate with a shell "no such file"
rather than a contract refusal. That is a known rough edge in the fingerprint-versus-fit
distinction, not a silent one.

## Still unverified

- whether `dependency:get` is a meaningful reachability check against a repository with a
  sync delay, and whether it needs `-DremoteRepositories`;
- whether `-DskipTests` on `deploy` is right, or whether the gate having already run
  `verify` makes it redundant rather than necessary;
- whether `deploy` succeeds without `distributionManagement` — it does not, and this
  adapter does not check for it, so a repository with no configured repository fails at
  publish time rather than at detection.
