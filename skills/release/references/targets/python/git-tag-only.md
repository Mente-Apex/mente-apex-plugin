---
technology: python
toolchain: git-tag-only
fingerprint:
  - .claude-plugin/plugin.json
  - pyproject.toml#tool.uv.package==false
version_source: .claude-plugin/plugin.json#.version
derived_manifests:
  - .claude-plugin/marketplace.json#.plugins[0].version
  - pyproject.toml#project.version
relock_command: uv lock
gate_command: uv sync && uv run pytest && uv run ruff check . && uv run black --check .
build_command: null
artifact_pattern: null
tag_pattern: v<version>
publish_command: git push <remote> <default> --follow-tags
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
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

**There is no wheel.** `pyproject.toml` declares `[tool.uv] package = false`, so `uv build`
would either fail or emit something nobody installs. `build_command` and
`artifact_pattern` are both `null`, and the core skips its build and artifact-verification
steps entirely. Do not "helpfully" add a build here.

**Do not confuse this with `python/uv`.** That adapter's fingerprint (`uv.lock`) is also
present in this repo — every uv project has one. `git-tag-only` wins on precedence because
its fingerprint is the more specific signal. If you ever find `/release` proposing a
`dist/*.whl` for this repo, detection picked the wrong adapter; fix the precedence table
in the contract rather than editing this file.

**The second fingerprint entry matches more repositories than this adapter fits.**
`pyproject.toml#tool.uv.package==false` is the honest generalisation of "builds no wheel",
and it selects this adapter for any such project — including one with no `.claude-plugin/`
directory, whose `version_source` and both `derived_manifests` would then address files
that do not exist. The contract's post-resolution check catches that and refuses. Do not
answer it by pointing `version_source` at `pyproject.toml`: this adapter's whole shape is
three mirrored plugin manifests, and a project without them wants a sibling adapter, not a
weakened one.

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
