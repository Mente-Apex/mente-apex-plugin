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
  version: "0.2.0"
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

This workflow names no technology and no forge. It knows only the fourteen-field adapter
contract in [references/ADAPTER-CONTRACT.md](references/ADAPTER-CONTRACT.md); the concrete
commands live in `references/build/<technology>/<toolchain>.md`.

That is deliberate and it is enforced: `tests/test_release_skill_structure.py` fails if
this file names a build tool. **Adding a release target means adding an adapter file, never
editing this workflow.** If you find yourself wanting to special-case a target here, the
contract is missing a field — extend the contract, not the core.

## Notation

Two substitution notations appear below and they are not the same thing:

- **`<angle-brackets>` in prose and in adapter values** — a placeholder from the contract's
  closed vocabulary, which *you* resolve and substitute before running anything. `<remote>`,
  `<default>`, `<version>`, `<tag>`.
- **`"$SHELL_VARIABLES"` inside a `bash` fence** — an ordinary variable, expanded by the
  shell that runs the block. `"$REMOTE"` and `"$DEFAULT"` are the same two values as
  `<remote>` and `<default>`; the notation differs only because a shell block can hold them
  and prose cannot.

A `bash` fence may carry both — `git tag -a "<tag>"` is a placeholder you resolve sitting
next to a command the shell runs. The test is who does the substituting: you, before the
call, for `<name>`; the shell, during it, for `$NAME`. A `<placeholder>` that reaches a
shell unresolved is a bug, not a variable the shell will fill in.

## Step 0 — Resolve the components and the distribution

### Discover the components

A repository may hold more than one buildable thing. Before any adapter is resolved, walk
the repository's **git-tracked** files for build evidence — the paths and predicates the
contract's Level 1 table names — and treat each directory that carries some as one
**component**.

Three rules, and they are the whole stage:

- **Only git-tracked files count as build evidence.** One rule rather than a list of
  directories to skip: generated, vendored and virtual-environment trees are ignored by
  git, so the walk excludes them without naming any of them, and it stays correct as a
  repository changes. A hand-written list does not.
- **Exactly one component → proceed silently.** That is every repository this skill runs
  against today, and the common path must not grow a question it never needed.
- **More than one component → stop and ask.** Never pick. Report what was found, with each
  component's resolved technology and toolchain, and mark exactly one **build and release**
  — the one this run cuts — and every other **check only**: a check-only component's gate
  runs, and nothing of it is stamped, tagged or published.

```
Found 3 components:
  .              python/uv        build and release
  dashboard/web  typescript/vite  check only
  worker         typescript/npm   check only
Correct?
```

The **root component carries the repository's release identity**: its adapter supplies
`tag_pattern` and `publish_command`, and no other component's does. A repository has one
tag and one outward-facing step no matter how many things it builds, so reading either
field from a subfolder would give one repository two release lines.

### Resolve the adapters

Read [references/ADAPTER-CONTRACT.md](references/ADAPTER-CONTRACT.md) and follow its
detection: components first, then within each component technology and then toolchain,
each by declared precedence.

Resolve the distribution separately, from shipping evidence at the repository root.
**Resolving no distribution adapter is legitimate** — a repository that builds, tags, and
ships nothing further beyond the tag is a complete shape, not a detection failure. Do not
reach for a near-fit adapter to fill the gap.

Load each component's resolved adapter file and hold its fourteen contract fields —
`version_source`, `gate_command`, `artifact_pattern`, `tag_pattern`, and the rest. **Every
later step reads through those fields, per component.** This is the only place a concrete
target enters the workflow.

A field's value may contain a placeholder from the contract's closed vocabulary —
`<remote>`, `<default>`, `<version>`, `<tag>`, `<release-notes-file>`, and
`<distribution-name:role>` for each role the adapter declares. Substitute each one as the
contract's placeholder table directs, and **refuse on any token outside that table**: an
unbound placeholder is a value you would have to guess, and a guess here publishes or
verifies the wrong thing. A
`<distribution-name:role>` whose role the adapter does not declare is unbound — including
when `distribution_names` is `null`, which is a claim that no command needs a name.

If a `distribution_names` selector resolves to a mapping rather than a value, the role is
that mapping's single key; **more than one entry is a refusal, not a choice** — ask which.

An adapter may also carry the `status` marker described below. It is a maturity flag on
the file, not a fifteenth contract field: no step reads through it, and the contract stays
fourteen fields wide.

Stop here if:

- **Several technologies match within one component** → ask which to release. Never guess.
- **No toolchain matches** inside a detected technology → ask, listing the available
  adapters for that technology.
- **Nothing matches at all** → refuse. Point the user at the contract's "Adding an
  adapter" section. Do not improvise commands.
- **The resolved adapter's `version_source` names a file that does not exist** → refuse and
  ask which adapter to use. A fingerprint may match on a predicate about the repository
  while the adapter still addresses manifests this repository has not got; substituting a
  different path would stamp a literal the adapter never declared.
- **The resolved adapter declares `status: stub`** → refuse, unconditionally. A stub has
  never driven a real release and its commands are unverified. Say which adapter was
  resolved and what it would take to promote it.

Report the resolution before continuing, so a wrong detection is visible immediately:

```
Target : python / uv-nobuild   (fingerprint: pyproject.toml#tool.uv.package==false)
```

## Step 1 — Inspect

Resolve `REMOTE` and `DEFAULT` with the shared procedure in
[../../docs/git-remote-resolution.md](../../docs/git-remote-resolution.md).

**Run that resolution and the block below inside a single shell invocation — one Bash
call.** Every tool call gets a fresh shell, so a variable set in one call does not exist
in the next: split across two calls, `"$REMOTE"` and `"$DEFAULT"` expand to empty strings,
the fetch is meaningless or fatal, and the workflow proceeds believing it fetched. Either
paste the resolution above this block, or re-resolve both values at the top of every block
that reads them.

```bash
# REMOTE and DEFAULT must already be set in THIS shell — see the shared procedure.
if [ -z "$REMOTE" ] || [ -z "$DEFAULT" ]; then
  echo "=== unresolved ===" ; echo "REMOTE=${REMOTE:-(none)} DEFAULT=${DEFAULT:-(unknown)}"
else
  git fetch --quiet "$REMOTE" "$DEFAULT"
  echo "=== behind ==="  ; git rev-list --count "HEAD..$REMOTE/$DEFAULT"
  echo "=== ahead ==="   ; git rev-list --count "$REMOTE/$DEFAULT..HEAD"
fi
echo "=== branch ==="  ; git branch --show-current
echo "=== status ==="  ; git status --short
echo "=== tags ==="    ; git tag --sort=-v:refname | head -5
```

The two resolution refusals below — no remote, unknown default branch — are decided from
the resolution output alone. **Check them first**, before reading anything that depends on
the fetch: an `=== unresolved ===` line means `behind` and `ahead` were never computed and
nothing may be inferred from their absence.

Read the adapter's `version_source` to get the current version. When `version_source` is
`null` there is no manifest literal to read — the current version is the most recent tag.

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
- **Local commits not on the remote** (`ahead` is non-zero). A release must not carry work
  the plan never listed — push them with `/ship` first, then re-run.
- **No remote.** There is nowhere to publish.
- **The default branch is unknown.** Resolution reported `(unknown — confirm with the
  user)`: no signal was found at any of its four layers. Never guess one. A guessed
  default branch cuts a release onto the wrong line of development, which is not
  recoverable by deleting a tag. Ask the user which branch is the release line and re-run.

**A merged pull request is not something the user has to announce.** After the fetch, a
merge is visible locally — it is why `behind` is checked rather than asked about. Never
ask "did you merge it?"; look.

## Step 2 — Preflight

Run **every** component's `gate_command`, in the order Step 0 listed them, each from its own
component's directory. Report a result per component, named — in a repository with three of
them, "the gate failed" says nothing about where to look.

**Check only is a component claim, and it is not the same as `build_command: null`.**
Marking a component check only says "this release is not building me" — a statement about
this run, made by whoever answered Step 0. `build_command: null` says "this toolchain builds
nothing, ever" — a statement about the toolchain, made by the adapter. They sit at different
levels and neither implies the other: a check-only component whose adapter declares a real
build command is still not built here, and a build-and-release component whose adapter
declares `build_command: null` still emits nothing at Step 6. What check only never means is
exempt from the gate. Every component is gated; only one is built.

Each gate begins with a clean rebuild from that component's lockfile for a reason worth
stating in the report: **that rebuild is a latent-dependency detector.** A test importing a
package that nothing declares passes indefinitely on the machine that happens to have it
installed, and fails the first time the environment is rebuilt. A release is the worst
possible moment to find out.

Non-zero exit from any component's gate → **refuse**, naming which component failed. Show
the failing output verbatim. Do not offer to fix it here; a red gate is a different job, and
mixing a fix into a release is how an unrelated change ships unreviewed.

## Step 3 — Verify there is exactly one version literal

Skip this step entirely when the adapter's `version_source` is `null`. That target keeps
no version literal in the tree at all — the tag is the version — so there is no canonical
occurrence to compare anything against, and every match would be prose.

Otherwise, search the repository for the current version string. Every occurrence must be
either the adapter's `version_source` or a declared entry in `derived_manifests`.

An undeclared occurrence → **refuse**, listing the file and line. It means either a
manifest that will silently keep the old version after stamping, or an adapter that is out
of date. Both are the procedure-drift failure this skill exists to prevent, and both are
one-line fixes once seen.

Exclude three kinds of path, none of them named after any particular repository:

- **Lockfiles.** One that records the project's own version is excluded here on purpose and
  handled in Step 5a — it is regenerated by the toolchain, never stamped.
- **Build output.** Generated, untracked, and about to be rebuilt anyway.
- **Documentation and planning directories** — changelogs, specs, plans, release notes,
  architecture decision records. These quote versions as *prose*, describing a release
  rather than declaring one, so an occurrence there is not drift.

Ask the user if the third category is ambiguous in their repository, and let the adapter or
the user name any further path to exclude. Do not extend the list on your own judgement: an
exclusion invented mid-release is how a real manifest gets skipped.

## Step 4 — Decide the version

Derive the proposed bump from Conventional Commits since the last tag:

- any `feat:` → minor
- only `fix:` / `refactor:` / `chore:` / `docs:` → patch
- any `!` or `BREAKING CHANGE:` → major

**Below `1.0.0` that last rule does not apply.** A `0.x` project has not promised
stability yet, so a breaking change proposes a **minor** bump — the leading zero stays.
Reaching `1.0.0` is a deliberate declaration the user makes, not something a commit
message triggers; the derivation never proposes it. When a breaking change is present on a
`0.x` version, say so and note that `1.0.0` is available if that is what the user means.

With no tags, fall back to commits since the last `chore(release):` commit; failing that,
the full history.

Show the reasoning, then let the user override — the derivation is a proposal, not a
ruling:

```
Version : 1.4.2 → 1.5.0   (minor: 4 feat, 2 fix since v1.4.2)
```

Once the version is settled — derived or user-chosen — **expand the adapter's
`tag_pattern` and hold the result as `<tag>`.** Every later mention of a tag reads that
string: the commit subject, the annotated tag, the checkpoint, the rollback commands, and
the report. Expand it here rather than at Step 8 because the refusal below needs it, and
because a tag the user is asked to confirm should be the one that will actually exist.

Then refuse if that tag already exists; Step 8 carries the rationale.

## Step 5 — Stamp

Skip this step entirely when the adapter's `version_source` is `null`. There is nothing to
stamp: the tag carries the version, no file records it, and writing one anywhere would
invent a literal the adapter never declared. Say so in the report and go to Step 6.

Otherwise write the new version to the adapter's `version_source`, then to every entry in
`derived_manifests`. All of them or none — a partial stamp leaves the manifests
inconsistent, which in a repo with a lockstep guard is a red suite and in a repo without
one is a silent wrong release.

**An entry whose file does not exist is a refusal** — the adapter names a manifest this
repository lacks, which means detection resolved an adapter that does not fit. Say which
file, and stop; nothing has been written yet, so there is nothing to revert.

**Unless the entry ends in `?`.** That is the contract's optional marker: the mirror is
legitimately absent in some repositories of this adapter's shape. Stamp it when present,
skip it when absent, and **say which in the report** — an unreported skip is the marker
being used to hide a path nobody has checked in months. The marker applies only to
`derived_manifests`; it is never valid on `version_source`, and a missing `version_source`
file was already refused back at detection.

**Hold what you actually wrote as the *stamped set*** — `version_source` plus every derived
manifest that was present, minus every optional one that was skipped. Steps 6 and 7 name
that set, never the adapter's raw list: a skipped optional entry is a path that does not
exist, and `git add` on a nonexistent pathspec **stages nothing at all** rather than
staging the rest. Reciting the declared list there would abort the release commit on
exactly the repositories the optional marker was added to support.

Show the resulting diff explicitly:

```bash
git --no-pager diff
```

The tree is now dirty, and deliberately so: nothing is tagged until the stamp is
committed, which is the point of the Steps 5 → 7 → 8 ordering. On the happy path Step 7
commits it. **If any later step refuses instead, that dirty tree is this skill's own
leftover** and must be reverted before re-running — Step 6 says how, and a refusal after
this point should always name the files it left behind.

## Step 5a — Refresh the lockfile

Relock **every** component whose adapter's `relock_command` is non-`null`, in the order Step
0 listed them. Skip a component whose `relock_command` is `null` — that component's lockfile
does not record the project's own version, so the stamp invalidated nothing. Skip the step
entirely when Step 5 was skipped: nothing was stamped, so nothing is stale.

Otherwise the stamp has just made the lockfile disagree with the manifest, and the lockfile
is not something to edit by hand — the toolchain regenerates it. Capture the tree's state,
run each component's command from that component's directory, and hold what it changed:

```bash
git status --porcelain          # before: the stamp's files, and nothing else
# for each component, from its directory: run that component's relock_command
git status --porcelain          # after: the difference is what the relock touched
```

**Hold the tracked files whose status changed as the *relocked set*** — the union across
every component that relocked. Step 7 stages them alongside the stamped manifests; that is
the whole point of running the commands here rather than leaving them to the build. Report
the set explicitly, per component — a relock that changed nothing is a fine outcome to
state, but an unstated one hides a command that silently did nothing.

Two refusals, each naming the component it happened in:

- **The command exits non-zero.** Report its output verbatim and stop. Step 5's stamp is on
  disk and uncommitted, so name the files to revert exactly as Step 6 does.
- **It changed a file that is untracked.** Never stage untracked output into the release
  commit — a lockfile that git does not track is a repository decision this workflow must
  not quietly reverse. Say which file, and stop.

If the relock changed more than the lockfile — dependency versions, a resolution — that is
an unreviewed dependency change riding into the release commit. Show the diff and say so;
the adapter's command is meant to be the narrow, manifest-only form.

## Step 6 — Build and verify the artifacts

Build **only** the components Step 0 marked *build and release* — today exactly one. A
check-only component was gated at Step 2 and stops there; nothing of it is built, stamped,
tagged or published, however much its adapter could build.

Skip this step entirely when that component's `build_command` is `null`.

Otherwise, for each component being built, run its command from that component's directory,
then **expand that component's `artifact_pattern` and check what actually landed**:

```bash
ls -1 <expanded artifact_pattern>     # per component being built
```

No match → **refuse**, naming the component. Report the pattern and what its build actually
emitted.

Step 5's stamp is on disk and uncommitted at this point, so the refusal is not finished
until it says how to undo it. Give the user the exact command, naming every file that was
stamped:

```bash
git checkout -- <each file in the stamped set> <each file in the relocked set>
```

Without that line the next `/release` refuses at Step 1 on a dirty tree the user never
made, with no clue where it came from. Do not run the revert unasked — the user may want
to inspect the stamp — but never leave it undocumented. Nothing to revert when
`version_source` is `null`; say that instead.

This is not defensive padding. In the reference repo the install documentation named a
wheel the build had never produced, and it stayed wrong for a long time because no step
ever compared the documented artifact against a real one. Assuming the artifact name is
how that happens; verifying it is how it stops.

## Step 7 — Commit

Skip this step entirely when the adapter's `version_source` is `null`. That target stamps
nothing, so there is nothing to commit and **there is no release commit** — the tag in
Step 8 points at the existing `HEAD`, which is already the reviewed, merged state of the
default branch. Never create an empty commit to have something to tag: an empty
`chore(release):` commit adds a second, contentless node to the release line and makes
`git show` on the tag say nothing. Say plainly in the report that no release commit was
made and which commit the tag will point at.

Otherwise: one commit, on the default branch, containing the stamp and the lockfile Step 5a
refreshed from it — and nothing else:

```bash
git add <each file in the stamped set> <each file in the relocked set>
git commit -F - <<'MSG'
chore(release): <tag>

<the co-author trailer this harness prescribes for the active model>
MSG
```

The trailer line is a placeholder like every other `<…>` in this file: resolve it from what
the harness prescribes this session and write that. It is spelled out rather than shown
because a literal here is a literal that gets copied, and the copy outlives the model it
named.

**Stage file paths, not selectors.** Every member of the stamped set is written as
`path#selector`; the selector addresses a field *inside* the file and means nothing to git.
Drop everything from the `#` onward and stage the path alone — passing the whole string
makes git report a nonexistent pathspec and abort. A trailing `?` goes with it. Two entries
that differ only in selector are one file: stage it once.

**Stage the relocked set too.** Step 5a held the tracked files its `relock_command` changed,
and they belong in this commit: a refreshed lockfile left unstaged is the stale-lockfile bug
with an extra step — the manifest and the lock still disagree at the tagged commit, and the
publish step finds out. These are plain paths already, with no selector to strip. Nothing to
add when `relock_command` is `null` or the relock changed nothing.

This is the one commit this skill makes, and it is the one commit `/ship` is structurally
forbidden to make — `/ship` never commits to the default branch. That is the whole reason
the work is not delegated.

## Step 8 — Tag

**Check first: the tag already exists** → refuse, before running anything below. Re-tagging
a released version is how two different commits end up claiming to be the same release. If
the user genuinely means to re-cut, they delete the tag deliberately, first. The stamp from
Step 7 is already committed at this point — undo it with `git reset --hard HEAD~1` before
doing anything else. If Step 7 made no commit because there was nothing to stamp, there is
nothing to reset: leave `HEAD` alone.

Step 4 already refused on this once, when it expanded `<tag>`. Checking again here is not
redundant: the two are separated by a gate, a build and a commit, and a tag can arrive from
another machine in between.

Then tag. Annotated, never lightweight — an annotated tag carries an author, a date, and a
message. The name is `<tag>`, expanded from the adapter's `tag_pattern` back at Step 4;
this workflow has no tag convention of its own, because `v1.2.3` is one ecosystem's habit
and not a universal one:

```bash
git tag -a "<tag>" -m "<tag>"
```

Everything up to here is local. Nothing has left the machine.

---

## ⚠ CONFIRMATION CHECKPOINT

The single stop in this workflow. Everything above was local and reversible; everything
below is not.

One qualification, so the promise matches what the commands deliver: the two rollback
commands undo the commit and the tag, and nothing else. If Step 6 ran a build, its output
is **untracked** — `git reset --hard` leaves it in place, and clearing it is a separate,
target-specific step. Nothing published, nothing lost; just say so rather than implying the
tree returns to exactly its prior state.

Show exactly what will leave the machine:

```
Release plan
  Target    : <technology> / <toolchain>
  Version   : <old> → <new>
  Stamped   : <version_source>, <derived manifests>, or "nothing to stamp"
  Relocked  : <the relocked set>, or "nothing — no lockfile records this version"
  Artifacts : <verified artifact names, or "none — no build for this target">
  Tag       : <tag>  (created locally)
  Will push : <publish_command>
  Then      : <release_command, or "nothing — the tag is the release">

  Not yet pushed. To abandon:
    git tag -d <tag>
    git reset --hard HEAD~1
```

Drop the second command if Step 7 made no commit.

Ask via **AskUserQuestion**. Anything other than a clear yes → stop and print the rollback
commands. Do not proceed on ambiguity.

---

## Step 9 — Publish

Run the adapter's `publish_command`, substituting every placeholder it carries as Step 0
directs — for most adapters that is the resolved `<remote>` and `<default>`.
Stop and report on any failure — never paper over a failed push, and never retry blindly.

A failure here is the one stop that lands on a *committed and tagged* default branch, so
say what state the repo is in and how to leave it. The rollback is the same two commands
the checkpoint printed:

```bash
git tag -d <tag>
git reset --hard HEAD~1
```

Drop the second command if Step 7 made no commit.

**A compound `publish_command` breaks that rollback.** Some adapters publish to a registry
*and then* push to git in one command. If the registry half succeeded and the git half
failed, **the rollback above is not safe and must not be offered**: the version is already
out in the world, immutable and installable, and deleting the local tag would leave a
published version that no commit in the repository claims. Do not re-cut it, do not bump
past it silently, and do not re-run the command hoping it is idempotent. Report exactly
that state — published, not pushed — name the version, and stop. Recovering is a decision
the user makes, and the usual answer is to push the tag by hand once the cause is fixed.

## Step 9a — Create the release object

Skip this step entirely when the adapter's `release_command` is `null`. That target's tag
*is* its release; there is no separate object to create. Say so in the report rather than
leaving a blank line where a URL would go.

Otherwise, group the Conventional Commits since the previous tag into release notes, write
them to a file, and run the adapter's `release_command` with `<release-notes-file>` bound
to that path and `<tag>` to the expanded tag. **Write the notes to a file rather than
inlining them**: commit subjects contain quotes, backticks and `$`, and a note substituted
into a command string is a note that can execute.

The forge is the adapter's business, not this workflow's. A repository on GitLab, Gitea,
or a self-hosted forge changes one field and nothing here.

**A failure at this step is not a failed release.** The push in Step 9 already happened —
the tag is public and the version is installable, so there is nothing to re-cut and the
rollback commands above no longer apply. This is the same shape as a missing or
unauthenticated forge CLI, which is the common case: the credential is absent, not the
release. Report it as a release that shipped **without its release object**, name the tag
that is live, show the command that failed, and stop. Do not retry, and do not offer the
rollback.

## Step 10 — Verify the install

Run the adapter's `install_verify_command`, substituting its placeholders as Step 0
directs. This is the command most likely to carry `<distribution-name:role>` and
`<version>`, so resolve those before running rather than pattern-matching past them.

Confirm two things:

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
  Commit    : <sha>  chore(release): <tag>, or "none — no manifest for this target"
  Tag       : <tag>  (pushed)
  Artifacts : <names, or "none">
  Release   : <url>, or "none — the tag is the release", or "not created — <reason>"
  Installed : <verified version>  → <resolved path>
  Skipped   : <each optional derived manifest absent from this repo>, omitted when none
```

**The `Skipped` line is not optional when a mirror was skipped.** An optional
`derived_manifests` entry that silently does nothing is the marker being used to hide a
path nobody has checked in months — a manifest renamed a year ago reports exactly like a
manifest that was never meant to exist here. Naming it every release is what keeps the
distinction visible; omit the line only when nothing was skipped.

The `Release` line has three honest answers and no fourth. Printing a URL
unconditionally — including on the degraded path where Step 9a failed — reports a release
object that does not exist, which is worse than saying nothing.

If anything stopped early, say exactly where and what the user must do to finish. A
partially completed release is worse than a refused one *only* if nobody says so.

## Scope — what /release does not do

- It does **not** commit or push ordinary work, and does **not** open a pull request. That
  is `/ship`.
- It does **not** merge pull requests, and does **not** run a code review.
- It does **not** fix a red gate. A failing suite refuses the release; repairing it is a
  separate job with separate review.
- It does **not** write adapters. Authoring one is deliberate — see the contract.
