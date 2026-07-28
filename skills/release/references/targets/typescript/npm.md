---
technology: typescript
toolchain: npm
fingerprint: package-lock.json
version_source: package.json#.version
derived_manifests: []
relock_command: npm install --package-lock-only
gate_command: npm ci && npm test && npm run lint
build_command: npm run build && npm pack
artifact_pattern: "*-<version>.tgz"
tag_pattern: v<version>
publish_command: npm publish && git push <remote> <default> --follow-tags
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
install_verify_command: npm install -g <distribution-name:package>@<version> && which <distribution-name:binary>
distribution_names:
  package: package.json#.name
  binary: package.json#.bin
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

**`package-lock.json` repeats the package's own version — twice.** Once in the root object
and once in the `""` entry of `packages`. So this adapter has the same shape the Rust one
documents: stamping `package.json` leaves the lockfile stale, `npm ci` then fails because
the two disagree, and the release commit carries a mismatched pair. `relock_command: npm
install --package-lock-only` refreshes the lock without touching `node_modules`; the core
runs it after the stamp and stages the result. Verify the flag against your npm version
before de-stubbing, and never widen it to a plain `npm install`, which re-resolves
dependencies and would smuggle an unreviewed upgrade into the release commit.

**`npm publish` is irreversible in a way tagging is not.** A published version cannot be
re-published, and unpublish windows are narrow. It sits after the confirmation checkpoint
for that reason. Verify the ordering against the core before trusting this adapter.

**Two-step publish.** Unlike the Python adapters, publishing touches a registry *and* the
git remote. Confirm the core handles a compound `publish_command` — or split it into a
registry step and a tag step and update the contract.

**`artifact_pattern` is a guess.** `npm pack` names the tarball from `name` and `version`
with scoped packages mangled (`@scope/pkg` → `scope-pkg-1.0.0.tgz`). Run a real `npm pack`
and correct the pattern before this adapter is trusted.

**npm needs two names, and they are declared as two roles.** `npm install -g` takes the
*package* name (`package.json#.name`); `which` takes the *binary* name, a key under
`package.json#.bin` that frequently differs — a package published as `@scope/my-tool` can
install a binary called `mt`. Assuming the two match is a real failure mode, so the
adapter declares `package` and `binary` separately rather than hoping one name serves.

What still needs verifying before de-stubbing: `package.json#.bin` may be a **string**
(shorthand, where the binary name equals the package name) rather than a table. Confirm
the `binary` role resolves correctly in both shapes, and that a scoped package installs a
binary whose name is unscoped.
