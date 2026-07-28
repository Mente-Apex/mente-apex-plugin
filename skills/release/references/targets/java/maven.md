---
technology: java
toolchain: maven
fingerprint: pom.xml
version_source: pom.xml#/project/version
derived_manifests: []
gate_command: mvn -B clean verify
build_command: mvn -B package
artifact_pattern: target/*-<version>.jar
publish_command: mvn -B deploy && git push <remote> <default> --follow-tags
install_verify_command: mvn -B dependency:get -Dartifact=<distribution-name:group>:<distribution-name:artifact>:<version>
distribution_names:
  group: pom.xml#/project/groupId
  artifact: pom.xml#/project/artifactId
status: stub
---

# java / maven  (STUB)

**This adapter has never driven a real release.** `/release` refuses to run against it.
Remove `status: stub` only after cutting a release with it.

## What to verify before removing the stub marker

**A Maven coordinate is two names, declared as two roles.** `group` and `artifact` are
separate selectors, and the `:` that joins them lives in `install_verify_command` where it
is Maven's syntax — not inside a selector value, where it would be the contract's. Verify
both resolve against a real multi-module POM, where `groupId` is frequently inherited from
`/project/parent/groupId` and absent from the child.

**Maven's version literal is not a leaf.** `pom.xml` has both `/project/version` and
`/project/parent/version`, and multi-module builds repeat the version in every child POM.
The core's single-literal check will find those and refuse. Decide before trusting this
adapter whether child POMs are `derived_manifests` (stamped) or whether the project uses
`${revision}` with a single property — the latter fits the contract cleanly, the former
needs every child listed.

**`mvn versions:set` exists and should probably be the stamp mechanism** rather than
editing XML directly. Confirm against the core's stamp step, which assumes a file rewrite.

**`clean verify` versus `clean test`.** `verify` runs integration tests and the full
packaging lifecycle, which is what a release gate should do. Do not weaken it to `test`.

**Deploying to Maven Central is not one command.** It needs GPG signing, a staging
repository, and a release action that is often manual. `publish_command` above is the
happy path for an internal repository only; a Central release needs the adapter — or the
contract — extended before it is honest.
