---
name: tdd
description: >-
  Test-Driven Development workflow enforcing a strict red-green-refactor cycle — one
  test at a time, never batching. Language-agnostic core with Python/pytest and
  TypeScript/Vitest (Jest-compatible) adapters;
  covers two kinds of work (building new features, and changing untested legacy code
  safely) and two entry modes: interactive (requirements interview first) and
  programmatic (invoked by another skill with requirements already gathered). Use
  whenever the user wants to implement a new feature, add functionality, write a new
  module, build a class, or do any implementation work. Trigger eagerly — "implement",
  "build", "create", "add feature", "write a function/class/module", "new endpoint",
  "I need to code", or anything that implies writing new production code, even if
  tests aren't mentioned. Also trigger on TDD, test-driven, test-first,
  red-green-refactor, or "write a failing test". Do NOT use this skill to diagnose or
  fix bugs — broken existing behavior belongs to the debug skill. Other skills can
  invoke this skill in programmatic mode to get code implemented test-first.
user-invocable: true
metadata:
  version: "1.5.0"
---

# TDD — Test-Driven Development

Never write production code without a failing test that demands it. Never write more
than one test before making it pass. This discipline is what makes the result
trustworthy: every behavior has a specification, and the specification ran red before
it ran green.

**This law governs *new behavior*.** A *refactor* adds no behavior, so it writes no new
failing test — its safety net is the *existing* suite (or, for untested code,
characterization pins written first). "Test-first" and "behavior-preserving refactor"
don't conflict; they are different work modes (below). Where this document later says
"write a failing test first," read it as the feature/legacy path, not the refactor one.

## How you were invoked

**Interactive** — a person asked for a feature or module. Run the requirements
interview (Phase 1) before building.

**Programmatic** — another skill, a plan executor, or an autonomous workflow invoked
you, or you're running somewhere nobody can answer questions. Skip the interview.
The caller should provide:

- the behaviors to implement, as acceptance criteria
- what's explicitly out of scope
- integration points (what existing code this touches)

If any of that is missing, derive it from the surrounding context, state your
assumptions in one visible block, and proceed — don't stall waiting for answers that
aren't coming. When done, report back: the tests written (their names should read as a
spec), the production code touched, and the final full-suite result.

This calling contract is the interface other skills depend on. Keep it stable — callers
should never need to know how the cycle works internally.

**Two independent axes — don't conflate them.** *How* you were invoked (interactive vs
programmatic) is separate from *what mode* the work is (feature / legacy / refactor,
below); any combination is valid — a programmatic legacy job, an interactive refactor.
And the acceptance-criteria handoff above is the **feature** contract. A caller
dispatching a **refactor** — most often a lens applying an approved recommendation —
uses the different, structured contract in
[references/refactor-jobs.md](references/refactor-jobs.md) (`targets` / `change` /
`coverage` / …), *not* the shape above. If you were handed a refactor job, read that
file first.

## Work modes

Pick based on what's being asked, not on how the user phrased it:

- **Feature** (default) — new behavior. Full cycle below.
- **Legacy** — the code you must change has no tests. Before changing anything, pin
  current behavior with characterization tests: call the code as it is and assert what
  it *actually does*. When current behavior looks wrong, flag it to the user instead of
  silently "fixing" it — that oddity may be load-bearing. Once the pins are green,
  switch to feature mode on top of that safety net.
- **Refactor** (programmatic) — a lens skill (`solid`, `gof`, `clean-architecture`,
  `test-quality`, the `code-quality` umbrella) asks you to apply a behavior-preserving structural
  change under a green safety net. Read `references/refactor-jobs.md` for the calling
  contract. In short: **verify the targets are genuinely covered first** (a `covered`
  label the suite never exercises is no net — and skipping this is how a refactor lands
  with no real safety), pin actually-untested targets first (legacy mode), apply the
  smallest faithful change, keep the full suite green, revert the whole job on red. A
  lens-applied refactor is *purely* behavior-preserving: it carries no `new_behavior`;
  a change that would alter behavior goes back to the human — it is not a refactor job.

**Not this skill: bugfixes.** When the task is that existing behavior is *wrong* — an
error, a wrong result, a regression — hand off to the debug skill rather than handling
it here; diagnosis is a different discipline with its own workflow. If a bug surfaces
mid-cycle (a characterization test exposes one, or the user reports one while you
work), flag it and let the user decide whether to divert — don't silently widen scope.

## Phase 1 — Understand (interactive mode only)

Before touching code, understand what you're building and why. Ask about: the behavior
(not the implementation), why it's needed, what's in and out of scope, edge cases,
acceptance criteria, and integration points. Start with the big picture and drill down
over two or three rounds — don't rapid-fire everything at once. Then summarize your
understanding back and get confirmation.

Also ask how the user wants to work:

- **Guided** — pause after each red-green-refactor cycle for review. Good for complex
  logic or when the user wants tight control.
- **Autonomous** — run the full implementation, stopping only when unclear or stuck.

If the user doesn't answer or can't be reached, default to autonomous, say so, and
leave a clear record of each cycle so the work is reviewable after the fact.

## Phase 2 — Build with red-green-refactor

### Open a working branch before the first file edit

Follow the plugin's git convention
([../../docs/git-convention.md](../../docs/git-convention.md)) — it is **authoritative**;
don't restate its ruleset here (a copy drifts — it already has). In short: on a git repo's
default branch, create and switch to `tdd/<short-slug>` (e.g. `tdd/rate-limiter-2026-07-06`)
before the first test file; on a feature branch, stay but say so; a dirty tree that
overlaps your targets stops you (ask interactively, flag it programmatically); no repo →
offer `git init`, and if declined proceed only after warning there's no revert seam. The
point: the user can review, land, or discard the whole session as one clean unit, and
nothing reaches a shared branch or remote without their say-so. A multi-step apply may
checkpoint-commit per verified step on the working branch (the convention sanctions this);
`/ship` curates the checkpoints into the final commit at the end.

**Programmatic mode**: if the caller already put you on a working branch, use it — the
outermost workflow owns the branch and its checkpoints. Only create `tdd/<slug>` when
you'd otherwise be editing the default branch.

### Discover conventions first

Scan the project before the first test: test directory layout, naming conventions,
shared fixtures, runner configuration, assertion style. Follow what exists — tests that
don't match the house style create friction for every future reader. For stack-specific
mechanics, load the matching adapter from `references/` (see "Language adapters"
below). In a greenfield project, use the adapter's defaults.

### The cycle

#### 1. RED — write exactly one failing test

One test, one behavior, with a name that reads like a spec
(`test_user_cannot_register_with_duplicate_email`). Arrange-Act-Assert. Run it and
confirm it fails because the behavior is missing — a test failing on an import error or
bad fixture proves nothing.

Writing multiple tests before implementing means making design decisions without
feedback. One test keeps the loop tight.

#### 2. GREEN — write the minimum code to pass

Just enough to turn the test green. No edge cases you haven't tested, no premature
abstraction. Ugly is fine here. Run the whole suite — everything must pass. Code not
demanded by a test is code without a specification.

#### 3. REFACTOR — clean up while green (mandatory)

Evaluate every cycle, even when the outcome is "nothing to refactor" — say so
explicitly. Silence is how this step evaporates.

**Measure first, then judge.** Run the probe over what this cycle changed:

```bash
sh "$CLAUDE_PLUGIN_ROOT/bin/mente-python" "$CLAUDE_PLUGIN_ROOT/scripts/complexity_probe.py" --scope working-tree --gate
```

It prints each changed function's complexity and length, then reports the
cycle-gate verdict. **Produce that output, or state why there isn't any** — no
probe for this language, tool absent, needs compiled classes. Either is a
complete answer; saying nothing is not.

The numbers are triage, never a verdict: a high count says *look here*, it does
not say *fix this*. The judgment is still yours, against the checklist below.

Per-cycle checklist (fast — run it every time):

- **Names** say what things are; no single-letter or abbreviated variables, including
  in comprehensions.
- **Functions** do one thing; a function doing two things gets split.
- **Duplication** in production code or tests gets extracted.
- **Nesting** stays shallow; no try/except as control flow.
- **Responsibility drift** — is this class accumulating a second reason to change?
- **Dependency direction** — high-level logic must not construct its own low-level
  dependencies (database clients, HTTP sessions, clocks). Inject them through the
  constructor or parameters. This is also what keeps the *next* test easy to write: if
  a test is hard to set up, this is usually the item that was skipped.
- **Mocking as a design signal** — mocking a true infrastructure boundary (network,
  clock, filesystem) is fine; needing to mock *your own* code to test it is a coupling
  smell — inject the collaborator instead of papering over it. (Hexagonal projects:
  `references/ddd_testing.md`. Auditing a whole suite for over-mocking is the
  `test-quality` lens's job, not this cycle's.)

Escalate beyond the checklist when it's warranted:

- For a deeper quality pass (or when the user asks "is this clean?"), use the
  `mente-apex:clean-code` skill if it's installed.
- When architecture-level smells recur across cycles — a god class every feature
  touches, type switches spreading between files — don't derail the cycle to fix them.
  Note the pattern and suggest a `/solid` audit as separate work. When the smell is
  specifically pattern-shaped — a missing, duplicated, or forced design pattern (a
  hand-rolled dispatch that wants Strategy, copy-pasted algorithm skeletons that want
  Template Method) — suggest a `/gof` audit instead.
- When the *tests themselves* have decayed — no module/class structure, pervasive
  over-mocking, or dead/duplicate tests in a suite that only grows — that's the
  `test-quality` lens (it uses coverage and mutation checks to prove a test still earns
  its keep). Suggest it rather than tidying the suite ad hoc mid-cycle.
- Running standalone without those skills? The checklist above is the whole standard;
  carry on.

Run the full suite after refactoring. If anything breaks, undo — you changed behavior,
which is not refactoring. (The interactive cycle runs the whole suite each pass. The one
exception is a *programmatic refactor job* on a large, slow suite, which may run a scoped
subset for its inner per-step checks with the full suite as the end gate —
`references/refactor-jobs.md`; that is an optimization of *when* the full suite runs, not
a licence to skip it.)

### Test ordering

Build complexity gradually: happy path → variations → edge cases → error cases →
integration concerns. If a test needs heavy scaffolding, write a simpler intermediate
test first.

### When things go wrong

- **Hard to write a test** → design smell, usually tight coupling. Restructure for
  testability rather than forcing the test.
- **One test breaks another** → hidden shared state or ordering dependency. Fix
  isolation before adding anything.
- **Major restructuring needed** → do it while green, in small steps, running tests
  between each.
- **The design is wrong** → rewrite the tests to match the corrected spec. Tests are
  specifications and specifications evolve — but *deleting* a test silently drops the
  coverage it carried, so delete only when the behavior it pinned is genuinely gone, not
  when it's merely in the way. Sweeping an existing suite for tests that have outlived
  their purpose is the `test-quality` lens's job (it coverage-gates every removal); don't
  improvise that mid-cycle here.
- **A test passes then fails with no code change (flaky)** → never paper over it with a
  retry. Find the nondeterminism — shared state, a real clock, ordering, an unawaited
  async, a live network call — and fix the cause, or quarantine the test with an explicit
  tracking note. A flaky test destroys the suite's signal, which is the one thing this
  whole discipline exists to protect.

## DDD / hexagonal projects

When the codebase uses ports-and-adapters, the testing strategy changes significantly —
read `references/ddd_testing.md`. The essentials: test the domain through its ports,
with no mocks — needing mocks for domain tests means the boundary is broken, and you
should warn the user. Adapter integration tests only when explicitly requested.

## Language adapters

The cycle above is language-agnostic; the mechanics are per stack. Adapters follow
the `references/<language>-<runner>.md` convention — detect the runner from the
repo, then load the matching file (list `references/` for the current set):

- **Python / pytest** → read `references/python-pytest.md` (fixtures, parametrize,
  raises, conventions discovery).
- **TypeScript / Vitest (or Jest)** → read `references/typescript-vitest.md`
  (`describe`/`it`/`expect`, `vi` spies/mocks, `it.each`, async `rejects.toThrow`,
  conventions discovery; Jest is covered by the compatibility note there).
- **Java / JUnit 5 (or 6)** → read `references/java-junit5.md` (AssertJ,
  Mockito, `@ParameterizedTest`, `@Nested`, Maven-vs-Gradle single-test
  invocation, Spring Boot test slices and why domain tests use no Spring at
  all; JUnit 6 is covered by the compatibility note there).
- **No adapter for this stack?** Discover the project's test conventions from the repo
  and apply the core cycle with the stack's standard test runner. Mention that an
  adapter reference could be added to this skill for next time.

## Learning and adaptation

Lessons from a session — fixture strategies, recurring smells, library gotchas — should
outlive the session. Read `references/learning.md` for how to persist them: it detects a
backend and degrades gracefully — a committed repo `memory/` dir, the Mente Apex brain
when present, else a short repo doc — so nothing here assumes an external memory system.
Always with the user's approval, never silently.

## Finishing

Run the full suite one last time and report the results honestly — including anything
skipped or still red.

Then, per the git convention: **offer, never auto-run.** Propose a Conventional Commit
summarizing the session and ask whether to commit and open a PR — the
`mente-apex:ship` skill is exactly that flow, so hand off to it when installed. "Leave
it on the branch" and "discard it" are first-class answers. Pushing and PR creation
are outward-facing: they need an explicit yes in this session, even when the build ran
autonomously.

**Programmatic mode**: don't commit at all. Leave the working tree as-is and report
back — publication decisions belong to the caller.
