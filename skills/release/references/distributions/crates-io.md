---
kind: crates-io
status: stub
fingerprint: Cargo.toml#package.publish
derived_manifests: null
install_verify_command: cargo install <distribution-name:crate> --version <version>
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
publish_command: null
distribution_names: null
---

# crates-io

Sketched, never exercised. See the contract's `status: stub` section.

**Unverified:** the fingerprint is inverted from what it should probably be —
`package.publish` is usually present only to *disable* publishing (`publish = false`), so
this likely needs a predicate rather than a presence check. Resolve it by running the
thing, not by reasoning about it.
