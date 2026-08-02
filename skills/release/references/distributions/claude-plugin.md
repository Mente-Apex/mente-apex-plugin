---
kind: claude-plugin
fingerprint: .claude-plugin/plugin.json
derived_manifests:
  - .claude-plugin/plugin.json#.version
  - .claude-plugin/marketplace.json#.plugins[0].version?
install_verify_command: claude plugin list
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>
publish_command: null
distribution_names: null
---

# claude-plugin

A repository that ships a Claude Code plugin manifest. The manifest tells the marketplace
which version to load, so it must be stamped in lockstep with whatever the build adapter
declares canonical — never lead it.

## Why the manifest is stamped and never canonical

`uv build` reads `[project].version` and bakes it into the wheel filename and its metadata,
so a version the plugin manifest led would be a version the build ignores. The stamp
direction follows whatever the toolchain actually reads.

Where the build adapter builds nothing (`python/uv-nobuild`), no toolchain reads either
literal, and the direction becomes a free choice. It still resolves the same way, so the
rule stays uniform: the build adapter always supplies `version_source`, and this file is
always downstream of it.

## `marketplace.json` is optional, and the `?` is load-bearing

A plugin repository that is also its own marketplace source carries a third mirror; one
publishing through somebody else's marketplace carries two. Both are this kind. Required-
and-absent would fail the stamp on the second; omitted entirely would let the third
mirror's literal read as undeclared drift and refuse at Step 3, mid-release, after the
gate. The marker is the only form under which both release correctly.

`plugin.json` has no `?` on purpose — a repository of this shape without one is not this
shape at all, and the strict entry is what says so.

## Verifying

`claude plugin list` must show the version just cut. A list still showing the previous
version is a consumer-side marketplace cache, not a failed release — the tag and the
manifests are correct, and the report says so. A *wheel* at the previous version is the
opposite: a real failure, and the one the axis split exists to make impossible.
