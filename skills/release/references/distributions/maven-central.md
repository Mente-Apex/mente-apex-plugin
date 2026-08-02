---
kind: maven-central
status: stub
fingerprint: pom.xml#/project/distributionManagement
derived_manifests: null
install_verify_command: mvn dependency:get -Dartifact=<distribution-name:group>:<distribution-name:artifact>:<version>
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
publish_command: null
distribution_names: null
---

# maven-central

Sketched, never exercised. See the contract's `status: stub` section.

**Unverified:** whether `distributionManagement` is present in every repository that
publishes to Central, and whether `dependency:get` is the right reachability check given
Central's sync delay.
