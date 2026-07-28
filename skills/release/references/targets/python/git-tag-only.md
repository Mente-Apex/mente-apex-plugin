---
technology: python
toolchain: git-tag-only
fingerprint: .claude-plugin/plugin.json
version_source: .claude-plugin/plugin.json#.version
derived_manifests:
  - .claude-plugin/marketplace.json#.plugins[0].version
  - pyproject.toml#project.version
gate_command: uv sync && uv run pytest && uv run ruff check . && uv run black --check .
build_command: null
artifact_pattern: null
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

**There is no wheel.** `pyproject.toml` declares `[tool.uv] package = false`, so `uv build`
would either fail or emit something nobody installs. `build_command` and
`artifact_pattern` are both `null`, and the core skips its build and artifact-verification
steps entirely. Do not "helpfully" add a build here.

**Do not confuse this with `python/uv`.** That adapter's fingerprint (`uv.lock`) is also
present in this repo — every uv project has one. `git-tag-only` wins on precedence because
its fingerprint is the more specific signal. If you ever find `/release` proposing a
`dist/*.whl` for this repo, detection picked the wrong adapter; fix the precedence table
in the contract rather than editing this file.

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
