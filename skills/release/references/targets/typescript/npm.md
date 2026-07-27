---
technology: typescript
toolchain: npm
fingerprint: package-lock.json
version_source: package.json#.version
derived_manifests: []
gate_command: npm ci && npm test && npm run lint
build_command: npm run build && npm pack
artifact_pattern: "*-<version>.tgz"
publish_command: npm publish && git push <remote> <default> --follow-tags
install_verify_command: npm install -g <package-name>@<version> && which <bin-name>
status: stub
---

# typescript / npm  (STUB)

**This adapter has never driven a real release.** `/release` refuses to run against it.
Remove `status: stub` only after cutting a release with it and correcting whatever the
commands below get wrong.

Its job right now is structural: it proves the adapter seam holds across a technology
boundary, not merely between two toolchains inside Python. If adding a second technology
had required editing the core, the seam would have been wrong — and this file is what
demonstrated it did not.

## What to verify before removing the stub marker

**`npm ci`, not `npm install`.** `ci` installs strictly from `package-lock.json` and fails
if the lockfile and `package.json` disagree. That is the latent-dependency detector for
this technology — the direct analogue of `uv sync`, and the same reason: a dependency that
is installed but undeclared has to fail *here*, not at a user's first install.

**`npm publish` is irreversible in a way tagging is not.** A published version cannot be
re-published, and unpublish windows are narrow. It sits after the confirmation checkpoint
for that reason. Verify the ordering against the core before trusting this adapter.

**Two-step publish.** Unlike the Python adapters, publishing touches a registry *and* the
git remote. Confirm the core handles a compound `publish_command` — or split it into a
registry step and a tag step and update the contract.

**`artifact_pattern` is a guess.** `npm pack` names the tarball from `name` and `version`
with scoped packages mangled (`@scope/pkg` → `scope-pkg-1.0.0.tgz`). Run a real `npm pack`
and correct the pattern before this adapter is trusted.
