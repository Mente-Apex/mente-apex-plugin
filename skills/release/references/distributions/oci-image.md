---
kind: oci-image
status: stub
fingerprint:
  - pom.xml#/project/properties/spring-boot.build-image.imageName
  - gradle.properties#imageName
derived_manifests: null
install_verify_command: docker manifest inspect <distribution-name:image>:<version>
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
---

# oci-image

Sketched, never exercised — see the contract's `status: stub` section. This is the
distribution adapter for a repository whose release is a **deployed container image**
rather than a package in a language registry: a Spring Boot service, not a library.

## The fingerprint is where this adapter is weakest

Every other distribution adapter in this skill fingerprints a fact its ecosystem already
records. This one has a harder problem: **a container image's name is not written down
anywhere neutral.** There is no `.npmrc` equivalent, no registry config file that exists
independently of the build. Spring Boot's buildpack support and jib both take the image
name as build configuration, so the only place to read it is the build manifest — which
is why both entries above are shipping selectors into shared manifests, the carve-out
the contract's separation rule defines.

The two entries are not equally solid, and the difference matters:

- **`pom.xml#/project/properties/spring-boot.build-image.imageName`** is a property
  **Spring Boot's own Maven plugin defines and reads**. Reading it is reading a fact the
  ecosystem records, exactly as `/project/distributionManagement` is.
- **`gradle.properties#imageName`** is a convention **this adapter imposes**. Gradle
  defines no standard property for an image name; a Gradle project that sets
  `imageName` in `bootBuildImage { }` directly, or derives it in code, records nothing
  this fingerprint can see. Such a project simply does not resolve this adapter — a
  missed detection, which is the safe failure, rather than a wrong one.

The contract records both facts in its shared-manifest table so the imposition is
visible there and not only here. If a durable convention for Gradle image names emerges,
this is the entry to replace.

**A `Dockerfile` was considered and rejected as the fingerprint.** It is absent from
exactly the projects this adapter targets — Spring Boot's buildpacks and jib both build
an image without one — and present in plenty of repositories that never publish one.
It would miss the intended case and claim unintended ones.

## `derived_manifests: null` — the image tag is not a mirror

An image's tag comes from `<version>` at push time; no file in the repository restates
it. There is nothing to stamp beyond what the build adapter's `version_source` already
covers, so this is a positive claim rather than an unfilled field.

The near-miss worth naming: a Kubernetes manifest or a Helm `values.yaml` pinning
`image.tag` **would** be a derived manifest, and a repository that deploys itself from
a chart in the same tree should list it here — as an [optional
entry](../ADAPTER-CONTRACT.md#optional-derived-manifests) if some repositories of this
shape carry it and others do not. That is a real variant of this adapter and the most
likely reason someone edits this file next.

## `install_verify_command` proves the push, not the build

`docker manifest inspect` queries the **registry** for the pushed tag, so it fails if
the image never arrived, and it does so without pulling the layers. It is the counterpart
to the build adapter's own `install_verify_command`, which greps the local jar for
`BOOT-INF/` — the contract's "`install_verify_command` goes on both, and both run".
Two checks of two different things: one that the build produced a real boot jar, one that
the registry now serves an image at this version.

Both build adapters declare the `image` role this command binds against; a distribution
adapter carries no `distribution_names` map of its own.

## `release_command` is the forge, and it is genuinely separable here

A GitHub release object is more useful for a deployable than for a library — it is where
the changelog for a deployed version lives, since there is no package page to carry it.
It is still the forge's concern rather than this adapter's, and the contract's known wart
about forge commands living in adapters applies unchanged. A repository on GitLab needs
the `glab` form.

Per the contract, a failure here is **not a failed release**: it runs after the image is
pushed, so by the time it can fail the version is deployed. It reports as a release that
shipped without its release object.

## Still unverified

- whether `docker manifest inspect` is the right reachability check against a private
  registry, or whether it needs a prior `docker login` the core does not perform;
- whether `crane digest` or `skopeo inspect` would be a better choice — neither requires
  a Docker daemon, and the daemon requirement is a real constraint in CI;
- whether a repository can legitimately resolve **both** this adapter and
  `maven-central.md` (a service that also publishes a shared client library), and
  whether the two `install_verify_command`s then both run cleanly. The contract permits
  any number of distribution adapters to match, so this should work; it has not been
  tried.
