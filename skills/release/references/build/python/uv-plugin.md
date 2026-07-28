---
technology: python
toolchain: uv-plugin
fingerprint: uv.lock+.claude-plugin/plugin.json
version_source: pyproject.toml#project.version
derived_manifests:
  - .claude-plugin/plugin.json#.version
  - .claude-plugin/marketplace.json#.plugins[0].version?
relock_command: uv lock
gate_command: uv sync && uv run pytest && uv run ruff check . && uv run black --check . && npm --prefix dashboard/web ci && npm --prefix dashboard/web test && npm --prefix worker ci && npm --prefix worker test
build_command: uv build
artifact_pattern: dist/*-<version>-py3-none-any.whl
tag_pattern: v<version>
publish_command: git push <remote> <default> --follow-tags
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
install_verify_command: uv tool install --force . && which <distribution-name:binary> && claude plugin list
distribution_names:
  binary: pyproject.toml#project.scripts
---

# python / uv-plugin

A `uv`-managed Python project that builds a wheel **and** ships a Claude Code plugin from
the same tree and the same version. Both halves are released by one tag: the wheel puts a
CLI on the user's `PATH`, the plugin manifest tells the marketplace which version to load,
and the two must never disagree.

Its Python command set is `python/uv`'s, verified in
Mente-Apex/menteapex-memory-system#202; read [uv.md](uv.md)'s traps as if they were written
here, because they are all still true. **What it adds is genuinely new and was not inherited
from anywhere**: a second stamped manifest, two JavaScript suites in the gate, and a
plugin-list check after the install. Those were exercised against `mente-apex-memory` when
this adapter was written — not assumed — because "it is just `uv` plus declared fields" was
the first draft's claim and it was not true.

Derived from `mente-apex-memory`, the repo that exposed the gap.

## Why this adapter exists

`git-tag-only` and `uv` between them held the two facts about such a repo and neither held
both. `git-tag-only` claimed it — a `.claude-plugin/plugin.json` was a fingerprint entry
there — and would have cut a tag with `build_command: null`, shipping a release that never
built the wheel it exists to publish. `uv` builds correctly but declares
`derived_manifests: []`, so the version literal in `plugin.json` reads as undeclared drift
and Step 3 refuses.

Both outcomes were the contract working: a fingerprint match is not a fit, and an
undeclared literal is a refusal rather than a guess. The answer is a third adapter, not a
loosened one.

## Traps

**Both fingerprint clauses are load-bearing; do not drop the `uv.lock` half.**
`.claude-plugin/plugin.json` alone reads like the obvious signal and is the same mistake
`git-tag-only` used to make with the same file. It says a repo is a plugin; it says nothing
about how the repo builds. Every command here is uv's, so a setuptools- or poetry-built
plugin repo matching on the manifest alone would pass detection, pass the post-resolution
`version_source` check (`pyproject.toml` exists in all of them), survive `uv sync`, and then
have `uv lock` **create a lockfile in a repo that deliberately has none** — refused at Step
5a, after the gate, after the stamp. The conjunction is what sends that repo to "no
toolchain matches → ask" instead.

**`pyproject.toml` is canonical and `plugin.json` is stamped — not the other way round.**
`git-tag-only` puts the plugin manifest first because there is no package for it to
contradict. Here there is: `uv build` reads `[project].version` and bakes it into the wheel
filename and its metadata, so a version the plugin manifest led would be a version the
build ignores. The stamp direction follows whatever the toolchain actually reads.

**`marketplace.json` is declared optional, and that `?` is load-bearing.** A plugin repo
that is also its own marketplace source carries a third mirror; one that publishes through
somebody else's marketplace carries two. `mente-apex-memory` is the second kind today and
could become the first without changing anything else about its shape, so both belong to
this adapter. Required-and-absent would fail the stamp on it; omitted-entirely would let
the third mirror's literal read as undeclared drift and refuse at Step 3, mid-release,
after the gate. The marker is the only form under which both repos release correctly.

It is not a licence to declare speculative paths. `plugin.json` above has no `?` on
purpose — a repo of this shape without one is not this shape at all, and the strict entry
is what says so.

**The gate crosses a language boundary, on purpose — and `dashboard/web` is the half that
must not be forgotten.** `[tool.setuptools.packages.find]` includes `dashboard*`, so the
dashboard **ships inside the wheel**: its TypeScript suite guards code that the release
actually distributes, which makes it the strongest claim on this gate of anything here.
`worker/` is the opposite case — a Cloudflare Worker that ships in no artifact — but it is
the only check on the MCP recall path, so a wheel cut while it is red releases half a
working system. Both are gated, for those two different reasons. An earlier draft gated
only the worker and justified it by what the wheel contains, which selected the one suite
whose code is *not* in the wheel.

**No credentials; not "no network".** Every suite here runs locally — miniflare's
SQLite-backed D1 for the worker's integration tests, with Workers AI and Vectorize injected
as fakes; jsdom for the dashboard. None needs a secret or a live Cloudflare account, which
is what makes them gateable at all; a suite wanting a real D1 would not belong here. But
`npm ci` installs from the registry, so **the gate as a whole needs the network** and will
fail offline. That is a deliberate trade for a clean, lockfile-exact install — the same
reason `uv sync` leads the Python half — and it is stated rather than glossed because an
earlier draft claimed this gate needed neither, which was false.

**The worker is gated, never deployed.** `wrangler deploy` is not in `publish_command` and
should not be added: the worker rolls on its own cadence, and folding it in would put a
deploy failure *after* the tag is already public. This adapter releases the wheel and the
plugin. The Worker is a separate act that this gate merely refuses to leave broken.

**A second repo of this shape without a `worker/` or `dashboard/web` directory splits this
adapter.** The gate names paths only one repository has. That is the same
near-repo-specificity `git-tag-only` carries and it is honest while the adapter describes
one repo; the moment it describes two, the answer is a sibling toolchain file, not a
conditional command. A gate that shell-guards its own steps can pass by skipping them,
which is the one thing a gate must never do — and note the failure here is *loud*:
`npm --prefix worker ci` in a repo with no `worker/` exits non-zero and refuses, rather
than quietly gating nothing.

**Private nested `package.json` files are not release manifests.** `mente-apex-memory` has
two, both `"private": true`. They publish nothing, so they are not derived manifests and
not a Level 1 technology match either — neither sits at the repository root. A `version`
field in one is a literal nobody consumes; delete it rather than declaring it, or it will
drift a release behind and Step 3 will never see it, because Step 3 searches for the
*current* version string.

## Verifying the install

Three things were released, so check all three:

```bash
uv tool install --force .
which <distribution-name:binary>                 # under ~/.local/bin, never the checkout
head -1 "$(which <distribution-name:binary>)"    # shebang points at the tool venv
<distribution-name:binary> --version             # prints the version just cut
claude plugin list                               # plugin entry reads the same version
```

The shebang check is [uv.md](uv.md)'s and carries its full weight here: a shim pointing
into the development checkout works perfectly for you and is broken for everyone else.

A `claude plugin list` still showing the previous version is a consumer-side marketplace
cache, not a failed release — the tag, the wheel and the manifests are correct, and the
report says so. A *wheel* at the previous version is the opposite: a real failure, and the
one this adapter was written to make impossible.
