---
technology: rust
toolchain: cargo
fingerprint: Cargo.lock
version_source: Cargo.toml#package.version
relock_command: cargo generate-lockfile --offline
gate_command: cargo build --locked && cargo test --locked && cargo clippy -- -D warnings
build_command: cargo build --release
artifact_pattern: target/release/<distribution-name:binary>
tag_pattern: v<version>
publish_command: cargo publish && git push <remote> <default> --follow-tags
install_verify_command: cargo install --path . && which <distribution-name:binary>
distribution_names:
  crate: Cargo.toml#package.name
  binary: Cargo.toml#package.name
status: stub
---

# rust / cargo  (STUB)

**This adapter has never driven a real release.** `/release` refuses to run against it.
Remove `status: stub` only after cutting a release with it and correcting whatever the
commands below get wrong.

It exists because Rust is the target that made `relock_command` necessary (#99). Every
other adapter could have been written without the field; this one could not, which is the
kind of pressure a seam is supposed to be tested under before it is trusted.

## The trap this adapter documents

**`Cargo.lock` records the crate's own version.** A workspace or binary crate commits its
lockfile, and that lockfile carries a `[[package]]` entry for the crate being built. So:

1. The core stamps `Cargo.toml`. `Cargo.lock` still says the old version.
2. `cargo build` silently rewrites `Cargo.lock` as a side effect.
3. Without a relock step the core stages only the manifests, and the release commit carries
   a manifest and a lockfile that disagree.
4. `cargo publish` then refuses — *after* the confirmation checkpoint, on a branch that is
   already committed and tagged. That is the single worst place in this workflow to stop.

`relock_command: cargo generate-lockfile --offline` closes it: the core runs it right after
the stamp, before the build consumes the lockfile, and stages the refreshed file into the
release commit. `--offline` keeps the resolution unchanged — a bare `cargo update` would
ride a dependency bump into a release nobody reviewed.

## What to verify before removing the stub marker

**`--locked` on the gate is this technology's clean-rebuild check.** It fails if `Cargo.lock`
would need to change, which is the direct analogue of `uv sync` and `npm ci`: a dependency
that resolves differently has to fail at the gate, not at a user's first build. Note the
interaction with the relock step — the gate runs at Step 2, *before* the stamp, so it
checks the lockfile as committed. Confirm that ordering behaves on a real release.

**`artifact_pattern` is a guess.** `cargo build --release` names a binary from
`[[bin]]`/`package.name` with hyphens preserved, emits `.exe` on Windows, and a library
crate emits `.rlib`/`.so` under the same directory instead. A workspace puts everything in
the *workspace root's* `target/`, not the crate's. Run a real build and correct the pattern
before trusting it.

**A workspace has more than one version literal.** Members inherit with
`version.workspace = true` from `[workspace.package]`, which is the shape that fits this
contract — one canonical literal, nothing derived. A workspace whose members each pin their
own version needs every member listed in `derived_manifests`, and the core's
single-literal check will refuse until they are.

**`crate` and `binary` are the same selector today and should not be assumed equal.** A
crate published as `my-tool` can declare `[[bin]] name = "mt"`. Split the `binary` role onto
the `[[bin]]` table before de-stubbing, and confirm it resolves for both the implicit and
the explicit shape.

**`cargo publish` is irreversible.** A published version cannot be replaced and yank does
not free the number. It sits after the confirmation checkpoint for that reason. It also
needs a registry token, and it runs its own verification build — expect the publish step to
take minutes, not seconds.

**`cargo install --path .` verifies the wrong thing if you are not careful.** It installs
from the working tree, which proves the source builds but not that the *published* crate
does. Once the crate is on a registry, prefer installing it by name and version so the check
exercises what a user actually gets.
