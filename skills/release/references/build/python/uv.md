---
technology: python
toolchain: uv
fingerprint: uv.lock
version_source: pyproject.toml#project.version
relock_command: uv lock
gate_command: uv sync && uv run pytest && uv run ruff check . && uv run black --check .
build_command: uv build
artifact_pattern: dist/*-<version>-py3-none-any.whl
tag_pattern: v<version>
publish_command: git push <remote> <default> --follow-tags
install_verify_command: uv tool install --force . && which <distribution-name:binary>
distribution_names:
  binary: pyproject.toml#project.scripts
---

# python / uv

A `uv`-managed Python project that builds a wheel. `pyproject.toml` holds the single
version literal; package metadata derives from it, so there is usually nothing to stamp —
`derived_manifests` is empty. If a project grows a second manifest carrying the version,
add it here rather than letting the core find an undeclared literal and refuse.

Derived from the verified release procedure in Mente-Apex/menteapex-memory-system#202.

## Traps

**The wheel name is not the project name.** `uv build` derives the artifact from
`[project].name` with dots and hyphens normalised to underscores, so a project named
`mente-apex-memory` emits `mente_apex_memory-0.4.0-py3-none-any.whl`. Install docs in that
repo told users to install `mente_apex_mem-*` for a long time, and nothing caught it
because no step ever compared the documented name against a real build. That is why
`artifact_pattern` exists and why the core *verifies* rather than assumes: expand the glob
after building and refuse if it matches nothing.

**The binary name is not the project name either.** `<distribution-name:binary>` for this
toolchain is the *key* under `[project.scripts]` — the shim `uv tool install` puts on
`PATH` — and it routinely differs from `[project].name`. A project named
`mente-apex-memory` whose `[project.scripts]` declares `mem = "..."` installs a binary
called `mem`; `which mente-apex-memory` finds nothing and the install check reports a
failure that is not real. The `binary` role selects the `[project.scripts]`
table and takes its key, never the project name. If the table holds more than one
entry the contract requires a refusal, not a choice — ask which entry point to verify.

This is the same error as the wheel-name trap above, one step later: the build artifact is
verified against a declared pattern, but the *installed* name was left to inference until
`distribution_names` bound it (#98).

**`uv.lock` pins the project itself, not only its dependencies.** The lockfile holds an
entry for the package being built, carrying the same version `pyproject.toml` declares, so
the stamp invalidates it immediately. `relock_command: uv lock` refreshes it in the one
window where the core can still stage the result — after the stamp, before `uv build`
consumes it, before the release commit. `uv lock` alone re-resolves nothing that is already
pinned; do not reach for `uv lock --upgrade` here, which would ride a dependency bump into a
release commit nobody reviewed.

**`uv sync` before the tests is the latent-dependency detector.** It rebuilds from
`uv.lock`. A test importing a package that no dependency declares — `uvicorn`, in the
reference repo — passes for weeks on the machine that happens to have it and fails the
moment anyone rebuilds cleanly. Running the sync first means the release discovers it,
not the user.

**Dependency layout is a release concern, not a style preference.** Tooling
(`pytest`, `ruff`, `black`) belongs in `[dependency-groups] dev`: `uv sync` installs it by
default and it never ships in the wheel. User-facing runtime extras belong in
`[project.optional-dependencies]`. Getting this backwards either ships test tooling to
users or makes `uv run` need flags — and it makes the clean-sync check meaningless,
because the wrong set gets installed.

**Never `pip`, `pipx`, `pyenv`, or `python -m build`.** There is one documented exception
in the reference repo — a pipx fallback inside install *code*, for foreign machines — and
it is not a path for cutting a release. Do not generalise it into this adapter.

## Verifying the install

Building a wheel proves nothing about what a user ends up running. Install the artifact
into an isolated tool environment and confirm the shim resolves **outside** the
development checkout:

```bash
uv tool install --force .
which <distribution-name:binary>                 # must be under ~/.local/bin, not the checkout
head -1 "$(which <distribution-name:binary>)"    # shebang must point at the tool venv
<distribution-name:binary> --version             # must print the version just cut
```

A shim whose shebang points into the development checkout means the "installed" tool is
the working tree — it will appear to work perfectly for you and be broken for everyone
else. That check is the difference between a build that succeeded and a release that works.
