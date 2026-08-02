---
kind: oci-image
status: stub
fingerprint: .oci-image.toml
derived_manifests: null
publish_command: ./mvnw -B -DskipTests spring-boot:build-image -Dspring-boot.build-image.imageName=<distribution-name:registry>/<distribution-name:repository>:<version> -Dspring-boot.build-image.publish=true && git push <remote> <default> --follow-tags
install_verify_command: docker manifest inspect <distribution-name:registry>/<distribution-name:repository>:<version>
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
distribution_names:
  registry: .oci-image.toml#registry
  repository: .oci-image.toml#repository
---

# oci-image

Sketched, never exercised — see the contract's `status: stub` section. This is the
distribution adapter for a repository whose release is a **deployed container image**
rather than a package in a language registry.

## `.oci-image.toml` — an opt-in file, and why it is not a build-manifest key

The image's name is not written down anywhere neutral in the JVM ecosystem. Spring Boot's
buildpack support and jib both take it as *build* configuration, so the obvious move is to
read it from `pom.xml` or `gradle.properties` — and an earlier revision of this adapter
did, arguing its way to a fourth shared manifest under the separation rule's carve-out.

That was wrong, and the contract now records why: **the carve-out exists for shipping
facts an ecosystem already records and you cannot move.** Gradle records no image name at
all, so the key would have been invented — and an invented fact can be invented in a
shipping-evidence file, which needs no carve-out. Reading it from a build manifest bought
nothing and cost the build adapters their ability to narrow their own fingerprints.

```toml
# .oci-image.toml
registry   = "ghcr.io"
repository = "mente-apex/billing-service"
```

Three things follow, and each fixes a defect the build-manifest version had:

- **The file's presence is the intent.** A repository carrying `.oci-image.toml`
  demonstrably means to publish an image. The previous fingerprint read a key that
  *nothing wired into the build* — declared, matched on, and then never used by
  `bootBuildImage`, so the image shipped under the plugin's default name while
  verification inspected the declared one. Here the same two values feed the publish and
  the verify, so they cannot disagree.
- **The tag is composed, never concatenated onto an existing one.** `registry` and
  `repository` are deliberately two roles with no tag component, so
  `<registry>/<repository>:<version>` is well-formed by construction. The previous
  version appended `:<version>` to a whole `imageName`, which produced `:latest` when the
  name was tagless and `app:1.2.3:1.2.3` — an invalid reference — when it was not. There
  was no shape of that field for which the command was correct.
- **It works for Maven and Gradle alike**, because it belongs to neither. That is the
  whole point of the field being on this axis.

## `publish_command` replaces the build adapter's

Declared here rather than in `java/maven` because pushing an image is orthogonal to which
build tool produced the jar — see the contract's section on this field. When this adapter
resolves, its command runs **instead of** `./mvnw deploy`, not alongside it: one
repository has one outward-facing step.

**The command above is Maven-only and that is a gap, not a design.** A Gradle repository
resolving this adapter would run `./mvnw`, which it does not have. The contract offers no
way to vary one field by the resolved build adapter, and the honest options are a second
distribution kind (`oci-image-gradle`, fingerprinted on the same file plus a Gradle build
file — the conjunction form exists for exactly this) or a contract field that maps a
command per technology. **Resolve this before using the adapter with Gradle.** It is
listed first among the unverified items below because it is the one that will actually
break.

## `derived_manifests: null` — the image tag is not a mirror

An image's tag comes from `<version>` at push time; no file in the repository restates it.
There is nothing to stamp beyond what the build adapter's `version_source` covers.

The near-miss worth naming: a Kubernetes manifest or a Helm `values.yaml` pinning
`image.tag` **would** be a derived manifest, and a repository that deploys itself from a
chart in the same tree should list it here — as an [optional
entry](../ADAPTER-CONTRACT.md#optional-derived-manifests) if some repositories of this
shape carry it and others do not.

## `install_verify_command` proves the push, not the build

`docker manifest inspect` queries the **registry** for the pushed tag, so it fails if the
image never arrived, and without pulling the layers. It is the counterpart to the build
adapter's own `install_verify_command` — the contract's "`install_verify_command` goes on
both, and both run". Two checks of two different things.

Two caveats the previous revision got wrong. `docker manifest inspect` **requires
`"experimental": "enabled"` in the Docker CLI config**, which is a real precondition and
not a footnote. And the reason to prefer `crane digest` or `skopeo inspect` is *not* that
they avoid a daemon — `docker manifest inspect` talks to the registry directly and needs
no daemon either — it is that they avoid the experimental flag and the Docker CLI
entirely.

## Still unverified

- **the Gradle gap above** — this adapter cannot currently publish from a Gradle build;
- whether `spring-boot:build-image` authenticates from the ambient Docker credential
  helper or requires `<docker><publishRegistry>` configured in the POM (it likely
  requires the latter, in which case `publish_command` is incomplete);
- whether `-DskipTests` is honoured by `build-image` or whether the plugin re-runs the
  lifecycle regardless;
- whether the image should be verified to be a *repackaged* boot jar before it is built —
  the build adapter's `artifact_pattern` cannot tell a boot jar from a plain one, and
  this adapter is the natural place to check;
- whether a repository can legitimately resolve **both** this and `maven-central.md` (a
  service that also publishes a client library) — the contract permits any number of
  distribution adapters to match, but two non-`null` `publish_command`s is an undefined
  conflict the contract does not currently rule on, and this adapter is the first that
  could create one.
