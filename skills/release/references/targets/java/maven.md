---
technology: java
toolchain: maven
fingerprint: pom.xml
version_source: pom.xml#/project/version
derived_manifests: []
relock_command: null
gate_command: mvn -B clean verify
build_command: mvn -B package
artifact_pattern: target/*-<version>.jar
tag_pattern: <distribution-name:artifact>-<version>
publish_command: mvn -B deploy && git push <remote> <default> --follow-tags
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
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

**The tag is not `v<version>`.** `maven-release-plugin` tags
`<artifactId>-<version>` by default, which is why `tag_pattern` reuses the
`artifact` role rather than restating the name — one declaration, two consumers.
Projects that have overridden `<tagNameFormat>` will disagree; read the POM
before trusting this. This is also the adapter that proves `tag_pattern` earns
its place: if every target wanted `v<version>` the field would be a constant.

**`mvn versions:set` exists and should probably be the stamp mechanism** rather than
editing XML directly. Confirm against the core's stamp step, which assumes a file rewrite.

**`relock_command` is `null`, and that is a claim, not a gap.** Maven resolves dependencies
at build time and commits no lockfile, so nothing in the tree can go stale when the POM is
stamped. A project that has adopted a third-party lock plugin has left that assumption
behind and must declare the refresh command here.

**`clean verify` versus `clean test`.** `verify` runs integration tests and the full
packaging lifecycle, which is what a release gate should do. Do not weaken it to `test`.

**Deploying to Maven Central is not one command.** It needs GPG signing, a staging
repository, and a release action that is often manual. `publish_command` above is the
happy path for an internal repository only; a Central release needs the adapter — or the
contract — extended before it is honest.
