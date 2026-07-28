---
technology: python
toolchain: uv-nobuild
fingerprint: pyproject.toml#tool.uv.package==false
version_source: pyproject.toml#project.version
relock_command: uv lock
gate_command: uv sync && uv run pytest && uv run ruff check . && uv run black --check .
build_command: null
artifact_pattern: null
tag_pattern: v<version>
publish_command: git push <remote> <default> --follow-tags
install_verify_command: null
distribution_names: null
---

# python / uv-nobuild

A `uv`-managed Python project that deliberately builds no wheel. `[tool.uv] package =
false` says so directly: the git tag *is* the release, `uv` manages the development
environment, and nothing is ever built or uploaded to an index. Whatever the repository
ships beyond the tag — a Claude Code plugin manifest, a config bundle, nothing at all — is
a separate, independently resolved distribution adapter; this file addresses only the
build side.

This is the build adapter for the `mente-apex-plugin` repo itself, which also resolves
`distributions/claude-plugin.md` — so it is exercised on every release of this skill.
Treat it as the reference instance for the build half; see that file for the distribution
half.

## Traps

**There is no wheel.** `pyproject.toml` declares `[tool.uv] package = false`, so `uv build`
would either fail or emit something nobody installs. `build_command` and
`artifact_pattern` are both `null`, and the core skips its build and artifact-verification
steps entirely. Do not "helpfully" add a build here.

**Do not confuse this with `python/uv`.** That adapter's fingerprint (`uv.lock`) is also
present in this repo — every uv project has one. `uv-nobuild` wins on precedence because
`package = false` is the more specific signal. If you ever find `/release` proposing a
`dist/*.whl` for this repo, detection picked the wrong adapter; fix the precedence table
in the contract rather than editing this file.

**This fingerprint says nothing about what the repository ships.** A `package = false`
project with no `.claude-plugin/` directory resolves this build adapter and no
distribution adapter at all — a legitimate shape, not a gap: it builds nothing, tags, and
ships nothing further. A `package = false` project that *does* carry
`.claude-plugin/plugin.json` additionally resolves `distributions/claude-plugin.md`,
independently, on that file's own fingerprint. Neither resolution constrains the other;
that independence is the whole point of splitting build from distribution.

**`version_source` names `pyproject.toml#project.version` even though nothing reads it.**
No toolchain consumes this literal — there is no build to consume it — so the choice of
canonical file is a free one rather than a forced one. It is still required: a target that
stamps nothing invalidates nothing, and the contract needs one canonical literal to stamp
regardless of whether a build reads it. Where a distribution adapter also resolves, its
`derived_manifests` are stamped *from* this value, never the reverse — see "Where the axes
tangle" in the contract.

**`uv.lock` carries this project's own version, so the stamp makes it stale.** Even with
`package = false` the root project has an entry in the lockfile, and it repeats the version
that `pyproject.toml` declares. Stamping the version without refreshing the lock would put
a mismatched pair in the release commit, and the next clean `uv sync` on anyone's machine
would rewrite the file the release claimed was current. That is why `relock_command: uv
lock` is declared: the core runs it after the stamp and stages `uv.lock` into the same
commit. It is not a `derived_manifests` entry because nobody edits a lockfile by hand.

**`uv sync` before the tests is not decoration.** It rebuilds the environment from
`uv.lock`, which is the only way a dependency that is installed-but-undeclared shows
itself. A test importing a package that no `[dependency-groups] dev` entry declares passes
indefinitely on the machine that happens to have it, and fails the first time anyone
rebuilds cleanly. A release is the worst moment to discover that, so the gate forces it
early and on purpose.

## Verifying the install

`install_verify_command` is `null`, and that is a positive claim, not an omission:
`build_command` is also `null`, so there is no wheel to reach an index or a `PATH`, and
nothing this adapter built can be verified as installed. Naming `claude plugin list` here —
a check of what a *distribution* adapter shipped, not what this build adapter built — would
be one side declaring the other half, and on a repository that also resolves
`distributions/claude-plugin.md` it would run the identical command twice.

Where a distribution adapter resolves alongside this one, its own
`install_verify_command` runs and is documented there — see
[claude-plugin.md](../../distributions/claude-plugin.md#verifying). Where none resolves,
there is nothing further to verify: the tag is the whole release.
