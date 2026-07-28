# Release-target adapter contract

The `/release` core workflow knows **nothing** about uv, npm, Maven, or wheels. It knows
only this contract. Every concrete release target supplies one adapter file filling these
fields; the core reads whichever file detection resolves and never names a technology
itself.

That is the whole design: **adding a release target means adding a file here, never
editing the core.** `tests/test_release_skill_structure.py` enforces it — the core failing
to stay technology-agnostic is a test failure, not a code-review opinion.

## Where adapters live

```
references/build/<technology>/<toolchain>.md
```

The directory is the technology (the detection axis). The filename is the toolchain (the
actual command set). One file is exactly one command set — one reason to change. A single
`python.md` branching uv-versus-poetry would have two, which is why the tree has two
levels.

## Build adapter fields

`references/build/<technology>/<toolchain>.md` — how a component builds and tests itself.
Declared as YAML frontmatter. Every field is required; several may be `null`.

| Field | Meaning | `null` allowed |
|---|---|---|
| `technology` | Must equal the parent directory name. | no |
| `toolchain` | Must equal the filename stem. | no |
| `fingerprint` | List of detection selectors; **any** match selects this adapter. Build evidence only. See [Fingerprint selectors](#fingerprint-selectors). | no |
| `version_source` | `path/to/file#selector` — the one canonical version literal. Selector language is the file format's; see [Selector syntax](#selector-syntax). | yes — targets where the tag itself is the version and no manifest carries it |
| `relock_command` | Regenerates the lockfile the stamp just invalidated. | yes — targets whose lockfile does not record the project's own version |
| `gate_command` | Clean rebuild from the lockfile, then the red/green check. | no |
| `build_command` | Produce distributable artifacts. | yes — no-build targets |
| `artifact_pattern` | Glob the build must emit. Verified, never assumed. | yes — iff no build |
| `distribution_names` | Map of *role* → `path/to/file#selector`, naming the installed thing. Same selector syntax. | yes — iff no command references `<distribution-name:…>` |
| `install_verify_command` | Proves the *built* thing installs. | no |
| `tag_pattern` | The tag this target's ecosystem expects. Expands to `<tag>`. Repo-level in effect — read only from the root component. | no |
| `publish_command` | The outward-facing step. Repo-level in effect — read only from the root component. | no |

A `null` `version_source` is not a shortcut for "we have not filled this in yet" — it is a
positive claim that the repository stores the version nowhere, because the git tag *is*
the version. Some ecosystems work this way: no manifest exists to stamp. The core skips
its single-literal check, its stamp, and its release commit for such a target; the tag is
created on the existing `HEAD` and nothing else changes.

A `null` `distribution_names` is likewise a positive claim: nothing this adapter runs needs
to name the installed thing. `python/uv-nobuild` builds no wheel and names no distribution,
so it declares `null`. Any adapter whose commands contain `<distribution-name:…>` must
declare every role it references.

## Distribution adapter fields

`references/distributions/<kind>.md` — what the repository ships beyond the tag, and how
you confirm it arrived. A repository may resolve **no** distribution adapter: that is the
empty square, where it builds, it tags, and nothing further mirrors or ships.

| Field | Meaning | `null` allowed |
|---|---|---|
| `kind` | Must equal the filename stem. | no |
| `fingerprint` | List of detection selectors; **any** match selects this adapter. Shipping evidence only. See [Fingerprint selectors](#fingerprint-selectors). | no |
| `derived_manifests` | List of `path#selector` stamped *from* the build adapter's `version_source`, same selector syntax. A trailing `?` marks an entry [optional](#optional-derived-manifests). | yes — empty list |
| `install_verify_command` | Proves the *shipped* thing arrived. | no |
| `release_command` | Creates the forge's release *object* from the pushed tag. | yes — targets where the tag is the whole release |

### The separation rule

> A build adapter may fingerprint only on **build evidence**. A distribution adapter may
> fingerprint only on **shipping evidence**. Neither may look at the other's.

- **Build evidence** — `uv.lock`, `package-lock.json`, `Cargo.lock`, `Cargo.toml`,
  `pom.xml`, `build.gradle`, `pyproject.toml`, `setup.py`, and predicates over them such
  as `pyproject.toml#tool.uv.package==false`.
- **Shipping evidence** — `.claude-plugin/plugin.json`, registry configuration, publish
  targets.

**This rule exists because the contract already walked into the failure it warned about.**
`.claude-plugin/plugin.json` — a fact about what ships — was a `git-tag-only` fingerprint
entry, so it decided a question about how a repository builds. The answer it produced,
`build_command: null`, was wrong: that repository has a setuptools backend and a console
script and builds a wheel perfectly well. `/release` cut a tag and never built it.

The release survived only because that project installs from source at the tag, so nothing
consumed the wheel that was never built. The safety came from an unrelated implementation
detail, not from this contract.

Adding a fourth adapter filled in the missing square. It did not remove the cause. Under
this rule the manifest has no path by which to reach `build_command`, which is a stronger
claim than "the missing adapter now exists".

**The rule is refined by selector, not by path, because Maven and Cargo have exactly one
manifest each.** `pom.xml` and `Cargo.toml` are simultaneously build evidence (they carry
the project's version) and the only place their ecosystem records a shipping fact —
`<project><distributionManagement>` and `package.publish` respectively. There is no second
file to redirect a distribution adapter's fingerprint to, the way `.claude-plugin/` sits
apart from `package.json`. So the evidence sets name **facts**, not files, and what
distinguishes "this fingerprint reads the manifest's build identity" from "this fingerprint
reads a shipping fact recorded inside it" is whether the fingerprint names a **selector**:

- A distribution adapter fingerprinting a **bare** build-evidence path (`pom.xml`,
  `Cargo.toml`) is still a violation — that is reading the file's identity, which is a
  build fact.
- A distribution adapter fingerprinting a **selector** into a build-evidence file
  (`pom.xml#/project/distributionManagement`, `Cargo.toml#package.publish`) is reading a
  named shipping fact recorded inside a shared manifest, not the file's build identity, and
  is not a violation.
- The build direction gets no matching latitude: `SHIPPING_EVIDENCE` stays matched on the
  whole path regardless of selector, because `.claude-plugin/` carries no build fact at any
  selector for one to disambiguate. A build adapter naming
  `.claude-plugin/plugin.json#.version` is still a violation.

That asymmetry is the point, not an inconsistency: the two evidence sets are not
structurally symmetric, because the shipping side has a file that carries no build facts and
the build side (for these two ecosystems) does not have the reverse.

### Where the axes tangle

Two fields do not cleanly belong to one side, and pretending otherwise would be the same
mistake at smaller scale.

**`distribution_names` goes on the build adapter, not the distribution adapter** — despite
the name. Every value it holds is a path the *toolchain* determines:
`pyproject.toml#project.scripts`, `package.json#.name` and `#.bin`,
`pom.xml#/project/groupId`. None is decided by what the repository ships. The naming
coincidence is not evidence.

**`install_verify_command` goes on both, and both run.** `uv tool install --force . && which
<distribution-name:binary>` verifies what the build produced; `claude plugin list` verifies
what the distribution shipped. They are two checks of two different things — a repository
running both is a `python/uv` build resolving alongside a `claude-plugin` distribution, and
each names only its own half. Forcing them into one field is what made that command a
compound in the first place.

**`version_source` always comes from the build adapter — which changes this repository's
canonical version file.** Before the axes were split, the two plugin-shaped adapters
disagreed about direction, and the disagreement was principled: `python/uv-plugin` made
`pyproject.toml` canonical because `uv build` reads it, while `python/git-tag-only` made
`.claude-plugin/plugin.json#.version` canonical, because a repository that builds nothing
has no toolchain reading `pyproject.toml` either. So which file led depended on what *reads*
the version, which is a shipping fact, not a build fact.

It collapses. In a `package = false` repository nothing builds, so no toolchain reads either
literal — both are stamped regardless, and only the arrow's direction differs. The direction
is therefore a free choice, and the uniform rule is cheaper than the faithful one: the build
adapter always supplies `version_source`, with no distribution-adapter override to reopen
the tangle. The stamp direction follows whatever the toolchain actually reads, everywhere
that rule has force.

Consequence for this repository: `pyproject.toml#project.version` is now canonical and
`.claude-plugin/plugin.json#.version` is derived, reversing the previous arrow. The same
files are stamped to the same values; only authority moves.

### Selector syntax

Four fields address a value *inside* a file: `version_source`, each entry of
`derived_manifests`, each value of `distribution_names`, and the predicate form of
`fingerprint` below. All four are written `path/to/file#selector`, and **the selector
language is determined by the file's format** — not by the field, and not by the adapter's
preference:

| File format | Selector language | Shape | Example |
|---|---|---|---|
| JSON — `.json` | jq path | leading `.` | `package.json#.version` |
| YAML — `.yaml`, `.yml` | jq path, as `yq` accepts it | leading `.` | `galaxy.yml#.version` |
| TOML — `.toml` | dotted key path | bare key first | `pyproject.toml#project.version` |
| XML — `.xml` | XPath | leading `/` | `pom.xml#/project/version` |

Each is the idiom a reader of that format already knows, and — more to the point — the
input the format's standard query tool already takes. The rule exists because it was
previously visible only by example: four adapters used three languages, an author had
nothing to follow, and the core had no way to know which parser a given selector wanted.

A format not in this table has no declared selector language, which is a refusal rather
than an invitation to improvise: add the row here first.
`tests/test_release_skill_structure.py` checks every selector in every adapter against its
file's row.

### Optional derived manifests

A `derived_manifests` entry may end in `?`:

```yaml
derived_manifests:
  - .claude-plugin/plugin.json#.version                    # required
  - .claude-plugin/marketplace.json#.plugins[0].version?   # stamp it if present
```

**Required is the default and stays strict**: an entry without `?` addressing a file that
does not exist is a **refusal**, before anything is written. Optional means exactly one
thing — *this mirror is legitimately absent in some repositories of this adapter's shape* —
and the core stamps it when the file is there, skips it when it is not, and reports which
it did.

The marker exists because one distribution shape spans repositories that differ in which
mirrors they carry. A plugin repo that is also its own marketplace source has three
manifests; one that publishes through somebody else's marketplace has two. Both resolve
`distributions/claude-plugin.md`. Without the marker the list forces a choice between an
adapter that fails the stamp on the two-manifest repo and one that lets the third repo's
literal read as undeclared drift — and the second failure lands at Step 3, mid-release,
after the gate has already run.

**Why a marker rather than "skip any absent entry".** Silently skipping absence would make
a *typo* — `marketplaces.json`, `.plugin/` — indistinguishable from a legitimately absent
mirror, and a mistyped entry would then read as a clean release that quietly stamped one
file fewer. That is the exact class of error this contract exists to prevent, so absence
must be **declared**, never inferred. "All of them or none" still holds; the marker only
changes which set "all" names.

The `?` is the contract's, not jq's. A jq path may legitimately end in `?` — its own
optional-value operator — and no selector here uses it; if one ever needs to, that is the
moment this marker moves to a separate field rather than the moment it grows an escape.
The marker is not available on `version_source` (a canonical version that might not exist
is not canonical), on `fingerprint` (an absent file simply does not match), or on
`distribution_names` (a name the command needs is not optional).

### Fingerprint selectors

`fingerprint` is a **list**, and each entry takes one of these forms:

| Form | Matches when | Example |
|---|---|---|
| `path/to/file` | that path exists | `uv.lock` |
| `path/to/file#selector==value` | that path exists **and** the selector resolves to `value` | `pyproject.toml#tool.uv.package==false` |
| `clause+clause` | **every** clause matches; each clause is either form above | `uv.lock+.claude-plugin/plugin.json` |

No form contains a space, so a folded list is unambiguous, and every `path#selector` half
obeys [Selector syntax](#selector-syntax) exactly like any other selector. An adapter with
one entry may write it inline — `fingerprint: uv.lock` — which is the same list, shortened.

**The list is OR; `+` is the AND the list cannot express.** Entries are alternatives —
*any* match selects the adapter — which is right for a target reachable by several
independent signals. No build adapter needs the conjunction today: build evidence and
shipping evidence now fingerprint on separate axes, each alone. It earned its place in the
vocabulary all the same — `python/uv-plugin`, before the axes were split, had to say "this
repo is both a uv project *and* a plugin" with `uv.lock+.claude-plugin/plugin.json`, because
`.claude-plugin/plugin.json` alone would have **confidently claimed** every non-uv Python
plugin repo — running `uv sync`, then `uv lock`, creating a lockfile in a repo that
deliberately has none, and refusing at Step 5a after the gate. A repo that no adapter fits
must reach "no toolchain matches → ask the user"; a fingerprint too weak to exclude it
converts that clean refusal into a confident wrong answer, which is the failure the
detection table's ordering rules already spend three paragraphs on. The form stays
available for the next adapter that needs it.

Keep clauses to the minimum that excludes what must be excluded. A conjunction is a
narrowing tool, not a description of the repository: piling on clauses that happen to be
true of the one repo you are looking at turns a shape into a fingerprint of a single
checkout, and the next repo of that shape silently falls through.

The field was originally a single file path while the Level 2 table already listed a
non-file selector for `python/uv-nobuild`. That contradiction left an adapter author with
no rule and the detection table making a promise the field could not keep: a `uv` project
declaring `[tool.uv] package = false` with no `.claude-plugin/` directory was told to use
that adapter's predecessor, whose fingerprint was demonstrably absent. The list closes it —
the table now mirrors the field, entry for entry, and a test fails if they drift.

**A fingerprint match is not a fit.** An adapter selected by a predicate can still address
manifests this repository does not have. Before the axes were split, `git-tag-only` named
`.claude-plugin/plugin.json#.version`, which a plain `package = false` project lacks — the
concrete case that motivated this check, and the one the split has since closed by giving
that project's build adapter (`python/uv-nobuild`) a `version_source` it always has
(`pyproject.toml#project.version`) and letting distribution resolve separately, or not at
all. The check stays as the general safety net for any future adapter whose fingerprint
outruns its own fields: **if the resolved adapter's `version_source` file does not exist,
refuse and ask.** Guessing a substitute path here would stamp a version into a file the
adapter never declared, which is the whole class of error this contract exists to prevent.

### Why a map and not a single name

One ecosystem's "name" is often several. npm installs by *package* name
(`package.json#.name`) and verifies the *binary* on `PATH`, which is a key under
`package.json#.bin` and frequently differs — `@scope/my-tool` can install a binary called
`mt`. Maven addresses a distribution by *two* coordinates, group and artifact.

A single field forces those cases either to be wrong or to smuggle syntax into the value —
encoding `groupId:artifactId` as one selector puts Maven's coordinate separator inside a
field the contract defines as one path and one selector. The map keeps each role a clean
selector and puts the ecosystem's joining syntax back in the command, where it belongs:

```yaml
distribution_names:
  group:    pom.xml#/project/groupId
  artifact: pom.xml#/project/artifactId
```
```
-Dartifact=<distribution-name:group>:<distribution-name:artifact>:<version>
```

Role names are the adapter's own vocabulary. A new naming role is a new key, never a new
contract field.

**A selector may address a table rather than a value** — `python/uv`'s binary name is the
*key* under `[project.scripts]`, not a value anywhere. When a selector resolves to a
mapping, the role's value is that mapping's single key. **If it holds more than one entry,
refuse and ask which** — do not pick. Guessing here is the whole failure this field exists
to prevent, and it would arrive at Step 10 where nothing else is checking.

### `relock_command` — a lockfile that records its own project's version

Most lockfiles pin *dependencies*, and a version bump does not touch them. Several pin the
project **itself**: `Cargo.lock` carries an entry for the crate being built, this repo's
own `uv.lock` carries `version = "…"` for the root project, and `package-lock.json` repeats
the package's version twice. For those targets the stamp in Step 5 makes the lockfile stale
the moment it lands, and nothing downstream notices until the toolchain refuses to publish
from a dirty tree — after the confirmation checkpoint, on a branch that is already
committed and tagged.

**Why this is not just another `derived_manifests` entry.** Entries there are `path#selector`
files the core *stamps*, by rewriting the addressed field. A lockfile is not stamped: it is
**regenerated** by the toolchain, from the manifest, with a hash and a resolution the core
has no business hand-editing. Listing it as derived would also collide with the core's
single-version-literal check, which excludes lockfiles precisely because they legitimately
repeat versions the adapter never declared.

So the adapter names a *command*, and the core runs it in the one window where its output
can still be staged — after the stamp, before the build that consumes it, before the commit:

```yaml
relock_command: uv lock                             # uv
relock_command: npm install --package-lock-only     # npm
relock_command: cargo generate-lockfile --offline   # cargo
relock_command: null                                # nothing pins this project's version
```

`null` is a positive claim, exactly like the other nullable fields: **stamping this target's
manifests cannot make anything stale.** Maven declares it — it has no lockfile at all.

The core stages whatever the command modified, so the command must be *narrow*. A relock
that also upgrades dependencies (`npm install`, `cargo update`) sweeps an unreviewed
dependency change into the release commit; prefer the offline, manifest-only form of your
toolchain's command and keep the resolution unchanged.

`relock_command` requires a non-`null` `version_source`: a target that stamps nothing
invalidates nothing, and `tests/test_release_skill_structure.py` fails the pair.

### `tag_pattern` — the tag convention is the target's, not the core's

`v<version>` looks universal and is not. A Go module at the repository root wants exactly
that; a Go **submodule** wants `sub/module/v1.2.3`, and the path prefix is not decoration —
the proxy resolves the module by it. `maven-release-plugin` defaults to
`<artifactId>-<version>`. Ruby gems and many monorepo conventions differ again.

So the pattern is the adapter's, and the core reads it as `<tag>` wherever it names a tag:
the annotated tag itself, the release commit's subject, the confirmation checkpoint, the
rollback commands, and the report. **`tag_pattern` is expanded once**, as soon as the
version settles in Step 4 — before the tag exists — because Step 4's "this tag is already
taken" refusal needs the resolved string too.

The pattern may use any placeholder in the vocabulary below **except `<tag>` itself**,
which is what it defines. Nothing else in the vocabulary is self-referential, so the
substitution has no cycle detection and is not going to grow any.

There is no `null` case. A target that builds nothing is ordinary; a target that publishes
nothing outward is conceivable; a release with no tag is not a release.

### `release_command` — the forge is a detail too

`publish_command` sends the version outward. What follows it — the *release object* on
GitHub, GitLab, Gitea, or a self-hosted forge — is a separate act, and it is the one the
core used to perform itself with a hardcoded `gh release create`. That made every non-
GitHub repository unreleasable without editing the core, which is precisely what this
contract exists to prevent.

`null` is a real value here, and a positive claim: **the tag is the whole release.** A
target publishing to a registry that has no notion of a release page declares `null`, and
the core skips the step exactly as it skips a `null` `build_command`.

```yaml
# GitHub
release_command: gh release create <tag> --title <tag> --notes-file <release-notes-file>

# GitLab — illustrative, never exercised here; verify the flags against your `glab`
release_command: glab release create <tag> --name <tag> --notes-file <release-notes-file>

# a registry-only target with no release page
release_command: null
```

**A failure here is not a failed release.** `release_command` runs after the push, so by
the time it can fail the tag is public and the version is installable. The core reports it
as a release that shipped without its release object — never as a release to re-cut. That
degradation is the core's rule, not the adapter's, so an adapter does not restate it.

**The known wart of putting this in the technology adapter.** The forge is genuinely
orthogonal to the language: a Python project and a Go project on the same GitLab instance
want the identical command, and here each would declare its own copy. That is accepted for
now — a second resolution axis costs a second detection procedure, a second precedence
table, and a merge rule, for a duplication that today spans four adapters and one forge. If
a third forge arrives and the copies start disagreeing, this field is the thing that gets
hoisted into a forge adapter; nothing here has to be unpicked first.

## The placeholder vocabulary

Commands and patterns may contain these tokens and **no others**. The list is closed: a
token outside it is a value the running agent has to guess, and a guessed distribution name
is exactly the error `artifact_pattern` exists to catch, arriving one step later at the
point where nobody is checking.

| Placeholder | Substituted from |
|---|---|
| `<remote>` | the resolution in [../../../docs/git-remote-resolution.md](../../../docs/git-remote-resolution.md) |
| `<default>` | the same resolution — the default branch |
| `<version>` | the version being released, as computed in Step 4 |
| `<tag>` | expanding this adapter's own `tag_pattern`; unavailable *inside* `tag_pattern` |
| `<release-notes-file>` | a path the core writes the grouped Conventional Commit notes to |
| `<distribution-name:role>` | reading the `role` key of the resolved `distribution_names` — see below for which adapter that is |

`<release-notes-file>` is a *path* rather than the notes themselves for a reason worth
stating: release notes are multi-line and routinely contain quotes, backticks and `$`.
Substituting them into a command string would make every adapter author responsible for
shell quoting, and the failure mode of getting it wrong is a release note that silently
executes part of a commit message.

Only roles the adapter actually declares are bound. `<distribution-name:binary>` in a
**build** adapter whose map has no `binary` key is an unbound token, exactly like
`<tool-name>` would be — which is also what makes a `null` map with a name-using command a
failure rather than an omission.

**A `<distribution-name:role>` token in a distribution adapter binds against the *root
build adapter's* `distribution_names` map** — the build adapter that resolves alongside it
for the same repository. `distribution_names` lives only on the build adapter (see "Where
the axes tangle" above) and gets no map of its own on the distribution side; a distribution
adapter's role tokens resolve against whichever build adapter's map that repository already
resolved, so nothing is declared twice. `npm-registry.md`'s `<distribution-name:package>`,
`maven-central.md`'s `<distribution-name:group>` and `<distribution-name:artifact>`, and
`crates-io.md`'s `<distribution-name:crate>` all resolve this way, against `typescript/npm`,
`java/maven` and `rust/cargo` respectively — each role was already declared there for the
build adapter's own `install_verify_command`, so the distribution stub introduces no new
role.

`tests/test_release_skill_structure.py` scans every field of every adapter for `<…>` tokens
and fails on any this table does not bind, so the vocabulary cannot drift open again. It
matches tokens permissively and subtracts the bound set — the inverse (matching only
well-formed tokens) would let `<TOOL_NAME>` or `<gemName>` through as "not a placeholder".

### `status: stub`

An adapter that has been sketched but never exercised against a real release declares:

```yaml
status: stub
```

The core **refuses to run** against a stub. A half-written adapter driving a real release
is exactly the failure this contract exists to prevent, so the refusal is unconditional —
no confirmation overrides it.

**Which makes "remove the marker after cutting a real release with it" circular**, and the
circle is worth naming rather than leaving each author to rediscover: the core will not run
a stub, so no release can ever be cut *with* one, so the marker can never be cleared by the
route that is supposed to clear it. Read literally, `status: stub` is not a probation
period — it is permanent.

The marker therefore means **"sketched, never exercised"**, and the exit is *exercising it*,
not releasing with it:

- **Author from a procedure already run by hand**, adapter-first: perform every command on
  the real repository, in order, and write down what actually happened. `python/uv` shipped
  unstubbed this way. So did `python/uv-plugin` — its inherited half was `python/uv`'s, and
  its three genuinely new parts (a second stamped manifest, two JavaScript suites in the
  gate, a plugin-list check) were each run against `mente-apex-memory` before being
  declared.
- **Declare `status: stub` when you have *not* done that** — a target sketched from an
  ecosystem's documentation, or from another adapter by analogy. `typescript/npm`,
  `java/maven` and `rust/cargo` are all this kind. Clearing the marker means going and
  running the thing, not waiting for permission the core will never grant.

"Inherited from a verified sibling" is not itself a licence: it covers the fields you
genuinely copied and nothing else. Every field you *changed* is unexercised until you
exercise it, which is the whole distinction the two bullets above turn on.

## The prose body

Frontmatter carries values. The body carries what key/value cannot: the traps.

`gate_command: uv sync && uv run pytest` does not say *why* the clean sync comes first —
that it is a latent-dependency detector, and that a test importing an undeclared package
passes for weeks on the machine that happens to have it installed. Put that in the body.
A field a future reader misapplies is a field that was documented as a value when it
needed to be documented as a reason.

## Detection

A stage, then two levels. Precedence is **declared here**, never emergent from directory
listing order.

### Stage 1 — components

Detection resolves *what* before it resolves *how*. A repository may hold several
**components** — directories that each build something — and the two levels below run
inside one component, not across the repository.

A component is a directory carrying **build evidence** in a **git-tracked** file. Only
tracked files count, which is one rule rather than a list of directories to skip:
generated, vendored and virtual-environment trees are ignored by git and so never enter
the walk, and the rule stays correct as a repository changes.

- **Exactly one component** → the core proceeds silently. Every repository releasing today
  is this shape, so the common path is unchanged.
- **More than one component** → the core stops and asks which is **build and release** and
  which are **check only**. It never picks.

Two fields are repo-level in effect and are read **only from the root component's build
adapter**: `tag_pattern` and `publish_command`. A repository has one tag and one
outward-facing step regardless of how many components it builds.

### Level 1 — technology

First match wins:

| Fingerprint | Technology |
|---|---|
| `pom.xml` or `build.gradle` / `build.gradle.kts` | `java` |
| `package.json` | `typescript` |
| `pyproject.toml` or `setup.py` | `python` |
| `Cargo.toml` | `rust` |

More than one technology matches **within a component** → **ask the user**. Never guess;
the wrong guess publishes the wrong thing.

Scoping the refusal to a component is what makes it usable. Repo-wide, it forbade exactly
the repositories this design exists to support: `mente-apex-memory` is a Python project at
the root beside a dashboard and a worker, and it escaped the old refusal only by accident —
its `package.json` files happen to sit in subfolders that the root-level check never
looked at. Scoping the refusal turns that accidental escape into the rule, and it
strengthens the refusal rather than relaxing it: a Python backend and a TypeScript
frontend genuinely sharing one directory now stops, where the repo-wide form would have
been satisfied by whichever fingerprint the table listed first.

### Level 2 — toolchain within that technology

First match wins:

Each row's fingerprint cell lists that adapter's `fingerprint` entries verbatim, joined by
`or`. The two must agree entry for entry; a test enforces it.

| Technology | Fingerprint | Toolchain |
|---|---|---|
| `python` | `pyproject.toml#tool.uv.package==false` | `uv-nobuild` |
| `python` | `uv.lock` | `uv` |
| `typescript` | `package-lock.json` | `npm` |
| `java` | `pom.xml` | `maven` |
| `rust` | `Cargo.lock` | `cargo` |

Note the ordering within `python` is load-bearing: both rows can match one repository,
because every uv project has a `uv.lock`. The two python rows read as one question asked in
narrowing order — **does it build a wheel at all?**

1. `package = false` → it builds no wheel at all, so `uv`'s `build_command` and
   `artifact_pattern` would both be wrong. This very repo. `uv-nobuild`.
2. Otherwise → an ordinary wheel-building uv project. `uv`.

The ordering also settles the `package = false` case that carries no `.claude-plugin/`
directory: it matches row 1's predicate and row 2's `uv.lock`, and the first row wins. That
repository resolves a build adapter and no distribution adapter — a legitimate shape, not a
gap: it builds nothing, tags, and ships nothing further.

**The resolved adapter's `version_source` file does not exist** → refuse and ask which
adapter to use. A fingerprint match is a signal, not proof of fit; see
[Fingerprint selectors](#fingerprint-selectors).

**No toolchain matches** within a detected technology → ask the user which adapter to use,
listing what is available.

**No technology matches at all** → refuse, and point the user at this file to write an
adapter. `/release` does not generate adapters interactively; authoring one is a separate,
deliberate act.

### Distribution detection

Distribution adapters resolve independently, by shipping evidence at the repository root —
`references/distributions/<kind>.md`'s own `fingerprint`, checked the same way a build
adapter's is. **Any** number may match, including **none**: a repository that builds and
tags but ships nothing further beyond the tag is a complete, legitimate shape, not a
detection failure. Where one does match, its `derived_manifests` are stamped from the
resolved build adapter's `version_source`, and its `release_command` and
`install_verify_command` run after the build side's own steps.

## Adding an adapter

First decide **which axis you are adding to**. An adapter that answers *how this component
builds and tests itself* is a build adapter; one that answers *what the repository ships
beyond the tag, and how you confirm it arrived* is a distribution adapter. The two live in
different directories, carry different field sets, and are detected differently.

1. Create the file with **its axis's field set** — a build adapter at
   `references/build/<technology>/<toolchain>.md` with the twelve
   [build adapter fields](#build-adapter-fields), a distribution adapter at
   `references/distributions/<kind>.md` with the five
   [distribution adapter fields](#distribution-adapter-fields). Do not mix them: a
   `build_command` on a distribution adapter, or a `derived_manifests` on a build adapter,
   is the axis tangle this split exists to remove.
2. On a build adapter, `tag_pattern` is the one people forget, because `v<version>` feels
   like a default rather than a choice, and `relock_command` is the one people get wrong:
   check whether your lockfile records the project's *own* version before declaring it
   `null`. On a distribution adapter, `release_command` is the one people over-fill — a
   target where the tag *is* the whole release declares it `null` rather than inventing a
   forge step.
3. Write the `fingerprint` under [the separation rule](#the-separation-rule), which
   constrains it by **fact, not by file**. A build adapter fingerprints build evidence
   only, matched on the whole path regardless of selector. A distribution adapter
   fingerprints shipping evidence only — and where the only manifest its ecosystem has is
   also build evidence, it must name a **selector** into the shipping fact it reads:
   `pom.xml#/project/distributionManagement` and `Cargo.toml#package.publish` pass, bare
   `pom.xml` and bare `Cargo.toml` do not.
4. Declare [`status: stub`](#status-stub) unless you authored it by running every command
   on a real repository first. The marker means "sketched, never exercised" — it is not a
   probation the core lets you serve, since it refuses to run against a stub at all.
5. **Build adapter only** — add its fingerprint row to the Level 2 table above, positioned
   so its precedence against existing adapters is explicit. The row's fingerprint cell must
   list the same entries the field does — a test compares them.
6. **Build adapter only, and only if the technology is new** — the first adapter under that
   directory — add a Level 1 row for it as well, again positioned deliberately. A Level 2
   row alone is unreachable: detection resolves the technology first, so an adapter whose
   technology no Level 1 fingerprint selects is never considered, and the run refuses with
   "nothing matches" while the adapter sits right there. Adding a toolchain to an *existing*
   technology needs Level 2 only.
7. **A new distribution kind needs neither table.** [Distribution
   detection](#distribution-detection) has no precedence table to add a row to: shipping
   evidence is matched directly, **any** number of adapters may match, and resolving
   **none** is a legitimate outcome rather than a detection failure. There is no ordering
   to declare because there is no first-match-wins to order.
8. Run `uv run pytest tests/test_release_skill_structure.py` — the guard checks both field
   sets, the directory/filename agreement, the separation rule, and fingerprint
   disjointness.

You do not touch `SKILL.md`. If you find yourself wanting to, the contract is missing a
field — add it here, to the field set it belongs to, to every adapter on that axis, and to
the test, in that order.
