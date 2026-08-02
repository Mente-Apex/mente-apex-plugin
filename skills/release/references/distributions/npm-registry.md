---
kind: npm-registry
status: stub
fingerprint: package.json#.private==false
derived_manifests: null
install_verify_command: npm view <distribution-name:package> version
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
publish_command: null
distribution_names: null
---

# npm-registry

Sketched, never exercised. `status: stub` means exactly that, and the core refuses to run
against it — see the contract's `status: stub` section for why "cut a release with it
first" cannot be the exit condition.

`derived_manifests` is `null` because `package.json` is the build adapter's
`version_source`, not a mirror of something else.

**Unverified:** the `npm view` flags, and whether `#.private==false` is the right
fingerprint or whether the absence of the key should also match.
