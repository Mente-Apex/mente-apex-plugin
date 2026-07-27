---
name: release
description: "Use when the user wants a new version cut and published — the gate → stamp → build → tag → publish → verify-install pipeline. Invoke on \"cut a release,\" \"release this,\" \"release 1.2.0,\" \"tag and publish,\" \"bump and release,\" \"publish the new version,\" \"ship a release,\" or \"/release.\" This skill OWNS versioning: it is the only place a version literal is bumped, derived manifests are stamped, artifacts are built and verified, a tag is created, and the installed tool is checked against what was just cut. Do NOT use for turning working changes into a commit and a pull request — that is /ship, which never touches versions. This skill never opens, reviews, or merges a pull request, and never runs a code review. It requires an up-to-date default branch: if a release PR is still open, merge it first, then invoke this."
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash, Read, Edit, AskUserQuestion
metadata:
  version: "0.1.0"
---

# release

Cut a version and get it out — gate, stamp, build, tag, publish, and then prove the
*installed* thing is the thing you just cut.

`/ship` ends at an open pull request. Everything after it is this skill. The boundary is
one line: **`/ship` never touches versions; `/release` never opens or merges pull
requests.**

Launching this skill is not consent to publish. Everything up to and including the local
tag is reversible with two commands; exactly one confirmation sits immediately before the
first thing that leaves the machine — never a second.

## The seam

This workflow names no technology. It knows only the ten-field adapter contract in
[references/ADAPTER-CONTRACT.md](references/ADAPTER-CONTRACT.md); the concrete commands
live in `references/targets/<technology>/<toolchain>.md`.

That is deliberate and it is enforced: `tests/test_release_skill_structure.py` fails if
this file names a build tool. **Adding a release target means adding an adapter file, never
editing this workflow.** If you find yourself wanting to special-case a target here, the
contract is missing a field — extend the contract, not the core.

## Step 0 — Resolve the adapter

Read [references/ADAPTER-CONTRACT.md](references/ADAPTER-CONTRACT.md) and follow its
two-level detection: technology first, then toolchain, both by declared precedence.

Load the resolved adapter file and hold its ten fields — `version_source`, `gate_command`,
`artifact_pattern`, and the rest. **Every later step reads through those fields.** This is
the only place a concrete target enters the workflow.

Stop here if:

- **Several technologies match** → ask which to release. Never guess.
- **No toolchain matches** inside a detected technology → ask, listing the available
  adapters for that technology.
- **Nothing matches at all** → refuse. Point the user at the contract's "Adding an
  adapter" section. Do not improvise commands.
- **The resolved adapter declares `status: stub`** → refuse, unconditionally. A stub has
  never driven a real release and its commands are unverified. Say which adapter was
  resolved and what it would take to promote it.

Report the resolution before continuing, so a wrong detection is visible immediately:

```
Target : python / git-tag-only   (fingerprint: .claude-plugin/plugin.json)
```

## Step 1 — Inspect

Resolve `REMOTE` and `DEFAULT` with the shared procedure in
[../../docs/git-remote-resolution.md](../../docs/git-remote-resolution.md). Then gather
the rest in one pass:

```bash
git fetch --quiet "$REMOTE" "$DEFAULT"
echo "=== branch ==="  ; git branch --show-current
echo "=== status ==="  ; git status --short
echo "=== behind ==="  ; git rev-list --count "HEAD..$REMOTE/$DEFAULT"
echo "=== ahead ==="   ; git rev-list --count "$REMOTE/$DEFAULT..HEAD"
echo "=== tags ==="    ; git tag --sort=-v:refname | head -5
```

Read the adapter's `version_source` to get the current version.

### Hard refusals

These are not confirmable. Say what is wrong and what would fix it, then stop.

- **Not on the default branch.** This workflow commits the version bump directly to the
  default branch, so the tag points at a commit that is actually on the release line.
  Being on a feature branch means the bump would be stranded.
- **The default branch is behind the remote** (`behind` is non-zero). Someone merged
  something you have not pulled. Tell the user to `git pull --ff-only` and re-run.
- **Dirty working tree.** List the modified paths. A release must be reproducible from
  what is committed; uncommitted work would either be swept into the release commit or
  silently excluded.
- **No remote.** There is nowhere to publish.

**A merged pull request is not something the user has to announce.** After the fetch, a
merge is visible locally — it is why `behind` is checked rather than asked about. Never
ask "did you merge it?"; look.

## Step 2 — Preflight

Run the adapter's `gate_command`. It begins with a clean rebuild from the lockfile for a
reason worth stating in the report: **that rebuild is a latent-dependency detector.** A
test importing a package that nothing declares passes indefinitely on the machine that
happens to have it installed, and fails the first time the environment is rebuilt. A
release is the worst possible moment to find out.

Non-zero exit → **refuse**. Show the failing output verbatim. Do not offer to fix it here;
a red gate is a different job, and mixing a fix into a release is how an unrelated change
ships unreviewed.

## Step 3 — Verify there is exactly one version literal

Search the repository for the current version string. Every occurrence must be either the
adapter's `version_source` or a declared entry in `derived_manifests`.

An undeclared occurrence → **refuse**, listing the file and line. It means either a
manifest that will silently keep the old version after stamping, or an adapter that is out
of date. Both are the procedure-drift failure this skill exists to prevent, and both are
one-line fixes once seen.

Exclude lockfiles, build output, and `docs/superpowers/` — plans and specs quote versions
as prose and are not stamped.

## Step 4 — Decide the version

Derive the proposed bump from Conventional Commits since the last tag:

- any `feat:` → minor
- only `fix:` / `refactor:` / `chore:` / `docs:` → patch
- any `!` or `BREAKING CHANGE:` → major

With no tags, fall back to commits since the last `chore(release):` commit; failing that,
the full history.

**If a tag for the derived version already exists, refuse.** Publishing over an existing
tag rewrites history a downstream consumer may have already pulled; the user must choose a
different version explicitly rather than have this workflow silently pick one for them.

Show the reasoning, then let the user override — the derivation is a proposal, not a
ruling:

```
Version : 0.21.0 → 0.22.0   (minor: 4 feat, 2 fix since v0.21.0)
```
