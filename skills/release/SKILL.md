---
name: release
description: >
  Use when the user wants a new version cut and published — the gate → stamp →
  build → tag → publish → verify-install pipeline. Invoke on "cut a release,"
  "release this," "release 1.2.0," "tag and publish," "bump and release,"
  "publish the new version," "ship a release," or "/release." This skill OWNS
  versioning: it is the only place a version literal is bumped, derived
  manifests are stamped, artifacts are built and verified, a tag is created,
  and the installed tool is checked against what was just cut. Do NOT use for
  turning working changes into a commit and a pull request — that is /ship,
  which never touches versions. This skill never opens, reviews, or merges a
  pull request, and never runs a code review. It requires an up-to-date
  default branch: if a release PR is still open, merge it first, then invoke
  this.
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

Show the reasoning, then let the user override — the derivation is a proposal, not a
ruling:

```
Version : 0.21.0 → 0.22.0   (minor: 4 feat, 2 fix since v0.21.0)
```

Once the version is settled — derived or user-chosen — refuse if its tag already exists;
Step 8 carries the rationale.

## Step 5 — Stamp

Write the new version to the adapter's `version_source`, then to every entry in
`derived_manifests`. All of them or none — a partial stamp leaves the manifests
inconsistent, which in a repo with a lockstep guard is a red suite and in a repo without
one is a silent wrong release.

Show the resulting diff explicitly:

```bash
git --no-pager diff
```

The tree is now dirty. That is expected and temporary — Step 7 commits it, and nothing is
tagged until it is committed. This ordering is the point of Steps 5 → 7 → 8.

## Step 6 — Build and verify the artifacts

Skip this step entirely when the adapter's `build_command` is `null`.

Otherwise run it, then **expand `artifact_pattern` and check what actually landed**:

```bash
ls -1 <expanded artifact_pattern>
```

No match → **refuse**. Report the pattern and what the build actually emitted.

This is not defensive padding. In the reference repo the install documentation named a
wheel the build had never produced, and it stayed wrong for a long time because no step
ever compared the documented artifact against a real one. Assuming the artifact name is
how that happens; verifying it is how it stops.

## Step 7 — Commit

One commit, on the default branch, containing only the stamp:

```bash
git add <version_source> <each derived manifest>
git commit -F - <<'MSG'
chore(release): v<version>

Co-Authored-By: Claude <noreply@anthropic.com>
MSG
```

Use the co-author trailer the harness prescribes for the active model this session.

This is the one commit this skill makes, and it is the one commit `/ship` is structurally
forbidden to make — `/ship` never commits to the default branch. That is the whole reason
the work is not delegated.

## Step 8 — Tag

Annotated, never lightweight — an annotated tag carries an author, a date, and a message:

```bash
git tag -a "v<version>" -m "v<version>"
```

**The tag already exists** → refuse. Re-tagging a released version is how two different
commits end up claiming to be the same release. If the user genuinely means to re-cut,
they delete the tag deliberately, first.

Everything up to here is local. Nothing has left the machine.

---

## ⚠ CONFIRMATION CHECKPOINT

The single stop in this workflow. Everything above was local and reversible; everything
below is not.

Show exactly what will leave the machine:

```
Release plan
  Target    : <technology> / <toolchain>
  Version   : <old> → <new>
  Stamped   : <version_source>, <derived manifests>
  Artifacts : <verified artifact names, or "none — no build for this target">
  Tag       : v<new>  (created locally)
  Will push : <publish_command>
  Then      : gh release create v<new>

  Not yet pushed. To abandon:
    git tag -d v<new>
    git reset --hard <remote>/<default>
```

Ask via **AskUserQuestion**. Anything other than a clear yes → stop and print the rollback
commands. Do not proceed on ambiguity.

---

## Step 9 — Publish

Run the adapter's `publish_command`, substituting the resolved `<remote>` and `<default>`.
Stop and report on any failure — never paper over a failed push, and never retry blindly.

Then create the GitHub release, with notes grouped from the Conventional Commits since the
previous tag:

```bash
gh release create "v<version>" --title "v<version>" --notes "<grouped notes>"
```

**`gh` missing or unauthenticated** → this is not a failed release. The tag is pushed and
the release is real. Report the tag, skip the GitHub release, give the user the
`releases/new` URL, and suggest `gh auth login` for next time.

## Step 10 — Verify the install

Run the adapter's `install_verify_command` and confirm two things:

1. The reported version is the one just cut.
2. The resolved binary lives **outside** the development checkout.

Point 2 is the one people skip. A shim whose path or shebang points into the working tree
means the "installed" tool is your checkout: it works perfectly for you and is broken for
everyone else. Building an artifact proves nothing about what a user ends up running.

A failure here does not un-publish anything — the tag is out. Report it plainly as a
release that shipped with an install problem, and say what is wrong.

## Step 11 — Report

```
✓ Released <version>
  Target    : <technology> / <toolchain>
  Commit    : <sha>  chore(release): v<version>
  Tag       : v<version>  (pushed)
  Artifacts : <names, or "none">
  Release   : <url>
  Installed : <verified version>  → <resolved path>
```

If anything stopped early, say exactly where and what the user must do to finish. A
partially completed release is worse than a refused one *only* if nobody says so.

## Scope — what /release does not do

- It does **not** commit or push ordinary work, and does **not** open a pull request. That
  is `/ship`.
- It does **not** merge pull requests, and does **not** run a code review.
- It does **not** fix a red gate. A failing suite refuses the release; repairing it is a
  separate job with separate review.
- It does **not** write adapters. Authoring one is deliberate — see the contract.
