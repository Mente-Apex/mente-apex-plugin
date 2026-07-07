---
name: tdd
description: >-
  Test-Driven Development workflow enforcing a strict red-green-refactor cycle — one
  test at a time, never batching. Language-agnostic core with a Python/pytest adapter;
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
  version: "1.3.0"
---

# TDD — Test-Driven Development

Never write production code without a failing test that demands it. Never write more
than one test before making it pass. This discipline is what makes the result
trustworthy: every behavior has a specification, and the specification ran red before
it ran green.

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

## Work modes

Pick based on what's being asked, not on how the user phrased it:

- **Feature** (default) — new behavior. Full cycle below.
- **Legacy** — the code you must change has no tests. Before changing anything, pin
  current behavior with characterization tests: call the code as it is and assert what
  it *actually does*. When current behavior looks wrong, flag it to the user instead of
  silently "fixing" it — that oddity may be load-bearing. Once the pins are green,
  switch to feature mode on top of that safety net.
- **Refactor** (programmatic) — a lens skill (`solid`, `gof`) asks you to apply a
  behavior-preserving structural change under a green safety net. Read
  `references/refactor-jobs.md` for the calling contract. In short: pin untested
  targets first (legacy mode), apply the smallest faithful change, keep the full
  suite green, revert the whole job on red. Any genuinely-new behavior the change
  introduces runs as a normal feature cycle.

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

This skill follows the plugin's convention for code-modifying skills
(`../../docs/git-convention.md`; the rules below are self-contained so the skill
also works standalone). The point: the user must be able to review, land, or discard the whole
TDD session as one clean unit, and nothing reaches a shared branch or remote without
their say-so.

- On a git repo's default branch (`main`/`master`) → create and switch to
  `tdd/<short-slug>` (e.g. `tdd/rate-limiter-2026-07-06`) before writing the first
  test file.
- Already on a feature branch → stay on it, but say so — the user may prefer a fresh
  branch off it.
- Dirty working tree → list the already-modified files first; if they overlap files
  this session must touch, stop and ask (interactive) or flag it in your report
  (programmatic).
- Not a git repo → say so and offer `git init`. If declined, proceed only after
  warning that there's no revert seam.
- **Programmatic mode**: if the caller already put you on a working branch, use it —
  the outermost workflow owns the branch. Only create `tdd/<slug>` when you'd
  otherwise be editing the default branch.

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

Escalate beyond the checklist when it's warranted:

- For a deeper quality pass (or when the user asks "is this clean?"), use the
  `mente-apex:clean-code` skill if it's installed.
- When architecture-level smells recur across cycles — a god class every feature
  touches, type switches spreading between files — don't derail the cycle to fix them.
  Note the pattern and suggest a `/solid` audit as separate work. When the smell is
  specifically pattern-shaped — a missing, duplicated, or forced design pattern (a
  hand-rolled dispatch that wants Strategy, copy-pasted algorithm skeletons that want
  Template Method) — suggest a `/gof` audit instead.
- Running standalone without those skills? The checklist above is the whole standard;
  carry on.

Run the full suite after refactoring. If anything breaks, undo — you changed behavior,
which is not refactoring.

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
- **The design is wrong** → rewrite or delete tests. Tests are specifications, and
  specifications evolve.

## DDD / hexagonal projects

When the codebase uses ports-and-adapters, the testing strategy changes significantly —
read `references/ddd_testing.md`. The essentials: test the domain through its ports,
with no mocks — needing mocks for domain tests means the boundary is broken, and you
should warn the user. Adapter integration tests only when explicitly requested.

## Language adapters

The cycle above is language-agnostic; the mechanics are per stack:

- **Python / pytest** → read `references/python-pytest.md` (fixtures, parametrize,
  raises, conventions discovery).
- **No adapter for this stack?** Discover the project's test conventions from the repo
  and apply the core cycle with the stack's standard test runner. Mention that an
  adapter reference could be added to this skill for next time.

## Learning and adaptation

Lessons from a session — fixture strategies, recurring smells, library gotchas — should
outlive the session. Read `references/learning.md` for how to capture them into the
Mente Apex memory brain (with the user's approval, never silently).

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
