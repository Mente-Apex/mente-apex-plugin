---
technology: python
toolchain: git-tag-only
fingerprint: pyproject.toml#tool.uv.package==false
version_source: pyproject.toml#project.version
relock_command: uv lock
gate_command: uv sync && uv run pytest && uv run ruff check . && uv run black --check .
build_command: null
artifact_pattern: null
tag_pattern: v<version>
publish_command: git push <remote> <default> --follow-tags
install_verify_command: claude plugin list
distribution_names: null
---

# python / git-tag-only

A Python-tooled repository that ships **no package**. The git tag *is* the release: a
Claude Code plugin, a config bundle, a skills collection. `uv` manages the development
environment, but nothing is ever built or uploaded to an index.

This is the adapter for the `mente-apex-plugin` repo itself, which means it is the one
adapter exercised on every release of this skill. Treat it as the reference instance.

## Traps

**`.claude-plugin/plugin.json` is canonical. The other two are stamped.** All three
manifests carry the same version literal, and `tests/test_skill_integrity.py::test_version_mirrors_match`
fails the build if they drift. Stamp all three or none — a partial stamp is a red suite,
which is the correct outcome but a confusing one to debug mid-release.

**`marketplace.json` is optional here for the same reason it is in `python/uv-plugin`.**
This adapter's fingerprint is `pyproject.toml#tool.uv.package==false`, which says nothing
about marketplaces — so it selects a `package = false` plugin repo published through
*somebody else's* marketplace just as readily as this one. A required entry would let that
repo pass detection and the gate and then refuse at Step 5 on a file it was never going to
have: the mid-release-after-the-gate failure the marker exists to prevent.

An earlier draft kept this entry strict on the argument that optionality is a property of
the adapter's *shape* and a repo of this shape always has all three mirrors. That argument
does not survive contact with the fingerprint, which is what actually selects the adapter
and which tests none of it. **Do not re-derive it.** The lockstep guarantee for *this* repo
does not come from the entry being required — it comes from
`tests/test_skill_integrity.py::test_version_mirrors_match`, which runs inside
`gate_command` and fails the release if the three manifests drift. That is a check against
the real files, not against a declaration, and it is the stronger of the two.

**There is no wheel.** `pyproject.toml` declares `[tool.uv] package = false`, so `uv build`
would either fail or emit something nobody installs. `build_command` and
`artifact_pattern` are both `null`, and the core skips its build and artifact-verification
steps entirely. Do not "helpfully" add a build here.

**Do not confuse this with `python/uv`.** That adapter's fingerprint (`uv.lock`) is also
present in this repo — every uv project has one. `git-tag-only` wins on precedence because
`package = false` is the more specific signal. If you ever find `/release` proposing a
`dist/*.whl` for this repo, detection picked the wrong adapter; fix the precedence table
in the contract rather than editing this file.

**A `.claude-plugin/` directory is not this adapter's signal, and used to be listed as
one.** The fingerprint once began with `.claude-plugin/plugin.json`, on the reading that a
plugin repository ships no package. That conflated two orthogonal axes: whether a repo
carries a plugin manifest, and whether it builds a wheel. A repository can do both —
`mente-apex-memory` publishes a real wheel with a `mem` entry point *and* a plugin
manifest mirroring the version — and the stale entry claimed it, winning precedence and
proposing a release that would cut a tag and never build or verify the package. That is
`python/uv-plugin`'s shape now, and this adapter's fingerprint is the single honest claim
it can make: **builds no wheel.**

**That one entry still matches more repositories than this adapter fits.**
`pyproject.toml#tool.uv.package==false` selects this adapter for any such project —
including one with no `.claude-plugin/` directory, whose `version_source` and both
`derived_manifests` would then address files that do not exist. The contract's
post-resolution check catches that and refuses. Do not answer it by pointing
`version_source` at `pyproject.toml`: this adapter's whole shape is three mirrored plugin
manifests, and a project without them wants a sibling adapter, not a weakened one.

**`uv.lock` carries this project's own version, so the stamp makes it stale.** Even with
`package = false` the root project has an entry in the lockfile, and it repeats the version
that `pyproject.toml` declares. Stamping the three manifests without refreshing the lock
would put a mismatched pair in the release commit, and the next clean `uv sync` on anyone's
machine would rewrite the file the release claimed was current. That is why
`relock_command: uv lock` is declared: the core runs it after the stamp and stages
`uv.lock` into the same commit. It is not a `derived_manifests` entry because nobody edits a
lockfile by hand.

**`uv sync` before the tests is not decoration.** It rebuilds the environment from
`uv.lock`, which is the only way a dependency that is installed-but-undeclared shows
itself. A test importing a package that no `[dependency-groups] dev` entry declares passes
indefinitely on the machine that happens to have it, and fails the first time anyone
rebuilds cleanly. A release is the worst moment to discover that, so the gate forces it
early and on purpose.

## Verifying the install

`claude plugin list` shows the installed marketplace plugins and their versions. Confirm
the entry for this plugin reads the version just cut. There is no shim or venv to check —
the plugin is loaded from the marketplace checkout, not installed into an environment.

If the version still shows the previous release, the marketplace has not re-fetched. That
is a consumer-side cache, not a failed release: the tag and the manifests are correct, and
the report should say so rather than implying the release failed.
