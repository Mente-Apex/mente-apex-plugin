# Shared refactor workflow (Phase 0–5)

Shared orchestration for the plugin's refactor lenses (`solid`, `gof`). Each
lens supplies a **rubric** (`references/<rubric>.md`) and a **report
template** (`references/report-template.md`); this file supplies the
workflow. The engine is TDD's refactor job
([skills/tdd/references/refactor-jobs.md](../skills/tdd/references/refactor-jobs.md)).
A lens's `SKILL.md` should link this file rather than restate the phases —
only the rubric and report template are lens-specific; everything below is
shared verbatim.

AI-generated code usually *works* but often reads badly: god classes, type
switches copy-pasted across files, business logic that instantiates its own
database client. A lens uses its rubric to find those problems, writes a
**refactor plan a human can actually evaluate**, and — only with sign-off —
applies it change by change with the test suite as a tripwire. The human is
always the editor; a lens never redesigns on its own.

**The cast** (you are the main agent / orchestrator):

| Role | Who | Instructions | Writes code? |
|------|-----|--------------|--------------|
| Orchestrator | you | this file | no |
| Analyzer | subagent | `docs/refactor-agents/analyzer.md` | no (read-only) |
| Reviewer | subagent | `docs/refactor-agents/reviewer.md` | no (writes only the report) |
| Implementer / TDD-coordinator | subagent | `docs/refactor-agents/implementer.md` | yes (approved recs only, via a TDD refactor job) |

All agent instruction paths above are relative to the plugin root. Dispatch
subagents with the Agent tool (`general-purpose`), telling each to read its
instruction file first. **If you cannot spawn subagents** (no Agent tool, or
you are already a subagent), play the roles yourself *sequentially and
honestly*: finish the analysis pass completely, then re-read the code fresh
for the verification pass before writing the final doc. The role separation
is what keeps false positives out of the report — don't collapse it.

## Invocation

`/<lens> [path]` — `path` scopes the analysis (default: repo root). The user
may also pre-authorize in the same breath ("apply everything Critical", "doc
only", "don't ask, use light verification"). **Pre-authorizations count as
the human review for whatever they cover — don't re-ask.** This also makes
the workflow usable non-interactively.

## Phase 0 — Inventory & baseline

Before any agent runs, establish ground truth yourself:

1. **Scope**: list the target tree (skip vendored/generated dirs: node_modules,
   .venv, dist, build, migrations, *_pb2.py, lockfiles). Note languages, rough
   size, entry points.
2. **Test suite**: detect it and record the exact command (see the lens's
   language references, or for other stacks the project's README/CI config).
   Then **run it once**. The baseline matters: a failure after a refactor is
   only attributable if the suite was green before it.
   - Baseline green → proceed.
   - Baseline red → tell the user which tests already fail; the apply phase may
     still run but only those pre-existing failures are tolerated afterward.
   - No suite at all → note it; the decision gate (Phase 3) handles it.
3. **Report dir**: create `docs/reports/<lens>/` in the target project (e.g.
   `docs/reports/solid/`) and git-exclude it — add `docs/reports/` to
   `.git/info/exclude` if the repo is a git repo and doesn't already ignore it.
   Reports are ephemeral working artifacts by default; the user may choose to
   commit a final report as a living doc at the end.

## Phase 1 — Analyzer

Spawn the analyzer with: the target path, the scope notes from Phase 0, and
instructions to read `docs/refactor-agents/analyzer.md` plus the lens's
rubric (`references/<rubric>.md`) — and the matching language reference where
one exists. It produces `docs/reports/<lens>/findings-draft.md` — evidence-backed
candidate findings, not yet trusted.

## Phase 2 — Reviewer

Spawn the reviewer with the draft path and the same references. The reviewer
re-opens the actual code for **every** finding, prunes what doesn't hold up,
re-tiers what does, hunts for cross-file violations the analyzer's
file-by-file pass tends to miss, and **cross-references the other lens** —
check [docs/lens-overlap.md](lens-overlap.md) for findings that overlap or conflict with
the sibling lens's territory so the two reports don't contradict each other —
before writing the final report to `docs/reports/<lens>/<LENS>-REPORT-<YYYY-MM-DD>.md`
using the lens's `references/report-template.md` **exactly**: the apply
phase depends on its structure (IDs, Risk and Status fields).

## Phase 3 — Decision gate (human)

Read the final report and present a compact summary: findings count by tier,
the top wins, and anything marked High risk. Then ask the user (AskUserQuestion)
which recommendations to apply — unless they already pre-authorized. **"None — I
just wanted the doc" is a first-class outcome**, not a failure; stop there gracefully.

**Grouped changes are approved as units.** When the report has a `## Grouped changes`
section, each group is one physical edit — present it by its **title + id** (e.g.
`group-1`) with its members (Primary; subsumed riders, which resolve automatically;
separable `Rides along` riders, which are optional). Approval works three ways, all
valid at once:

- **By tier** ("all Major") — a group is included when its **Primary's tier** matches;
  approving pulls the whole group in. (A group's tier is its Primary's tier.)
- **By group** ("apply group-1").
- **By id** — unchanged, for standalone recs that belong to no group.

The one sub-group choice is **vetoing a separable rider**: offer it only on `Rides
along` members. Subsumed riders are not vetoable — the Primary's single edit resolves
them, so excluding one means rejecting the group. A rider only lands **through its
Primary**: approving a Minor rider whose Primary is an unapproved Major does not apply
it. A report with no `## Grouped changes` section is approved exactly as before (by
tier or id).

If the project has **no test suite** and the user wants changes applied, ask
how to proceed — this choice becomes the `coverage` policy passed to the TDD
refactor job in Phase 4:

- **Stop at the doc** — safest, nothing is touched.
- **Characterization tests first** — the engine writes tests pinning
  current behavior of the code each approved rec touches, *before* refactoring
  it. Slower, safest apply path.
- **Light verification** — no suite; after each change the engine
  type-checks/compiles, imports every touched module, and smoke-runs the entry
  point. Make sure the user understands this catches breakage, not behavior
  drift.

## Phase 4 — Apply via TDD (tiered hybrid approval)

**Working branch first.** Before touching any file, follow the plugin's git
convention ([docs/git-convention.md](git-convention.md)): on a git repo's
default branch, create `<lens>/<short-slug>` and do all apply-phase work
there; surface a dirty tree before mixing changes into it. This is what lets
the human review, land, or discard the whole refactor as one unit.

Split the approved recommendations by their **Risk** field:

- **Low/Medium risk** → dispatched as described below.
- **High risk** (public API signatures, cross-module moves, anything
  behavior-adjacent) → confirm **each one individually** with the user first:
  show the recommendation and the planned change, get a yes/no, then dispatch.
  A blanket pre-authorization that explicitly includes high-risk items ("apply
  everything, including high-risk") satisfies this.

**Each approved rec is applied by dispatching a TDD refactor job** — the
shared engine at
[skills/tdd/references/refactor-jobs.md](../skills/tdd/references/refactor-jobs.md).
The implementer/TDD-coordinator role (`docs/refactor-agents/implementer.md`)
translates a rec into that engine's calling contract (`targets`, `change`,
`test_command` + `baseline_status`, `coverage`) and dispatches **one job
per group** (a declared `## Grouped changes` entry), **or one job
per rec** / dependent chain for ungrouped recs, **sequentially**, each with a fresh context.
One coordinator grinding through a long batch spends its shrinking context
window on the later recs — the widest change gets reasoned about in the
dregs. Per-rec contexts also isolate failure: a rec that reverts poisons
nothing downstream, and blame stays 1:1.

Order the queue first, then batch it:

- **Grouped changes are one job.** When the report declares a `## Grouped changes`
  entry, that whole group is a single refactor job — do **not** re-derive a batch from
  file overlap for it. The job applies the **Primary** (its subsumed riders resolve with
  that edit) and then each approved **separable** (`Rides along`) rider as a follow-on
  step in the same job.
- **Ungrouped recs apply per-rec, as before.** For any rec that belongs to no group,
  keep today's batching: recs touching the same file form one **chain** (same job
  runner, dependency order — a rec that moves code into a module another rec creates runs
  after it). This file-overlap chain is the fallback; a report with no `## Grouped
  changes` section drives this path identically to before.

Order the jobs Critical → Major → Minor (a group's tier is its Primary's tier). Give
each dispatch: the report path, its group id (or rec id / chain), the test command and
baseline status, and the coverage policy from Phase 3.

**Verification inside a group job.** Run the suite after the **Primary + subsumed** edit
— green lands the core fix as one unit. Then apply each approved separable rider and
verify it; a separable edit that breaks the suite **reverts alone**, leaving the Primary
green (an optional adjacent cleanup must never sink the core structural fix). The
refactor job updates Status and the Apply log in place and yields a structured summary
(`job_id`, `outcome`, `tests_written`, `files_touched`, `diffstat`, `suite_status`,
`noticed_not_touched`) — read it before dispatching the next.

**Parallel option** — for large approvals (roughly 6+ recs across disjoint
files) independent chains may run concurrently, each in its own git worktree
(`isolation: worktree`). Two hard rules: recs touching the same file never run
in parallel, and per-worktree green proves nothing about the combination —
after merging, run the full suite once on the merged tree yourself. Merged
suite red → fall back to the sequential contract: revert the merge and re-land
chains one at a time until blame is attributable. Parallelism is an
optimization; sequential is the contract.

## Phase 5 — Final review & loop

When a refactor job yields:

1. **Verify independently** — run the test suite yourself once; don't take the
   report's word for it. Compare against the Phase 0 baseline.
2. **Spot-check the diffs** for regressions of the cure: did a god-class split
   produce anemic pass-through wrappers? Did an extracted interface end up with
   one method per client anyway? New violations introduced by the refactor go
   into the next cycle.
3. **Loop or land.** If approved recs failed (reverted) or the spot-check found
   new Critical/Major issues, run another cycle — analyzer scoped to *changed
   files only*, then reviewer, then back to the human at Phase 3. **Hard cap: 3
   cycles**; a refactor loop that can't converge in three passes needs a human
   architect, not a fourth pass. Say so plainly.
4. **Summarize**: what was applied (rec IDs + diffstat), what failed and why,
   suite status before/after, and what remains in the doc for a future pass.
5. **Offer to commit and PR — never auto-publish.** Per the git convention,
   propose a Conventional Commit for the working branch and ask whether to
   commit and raise a PR (the plugin's `/ship` skill is exactly that flow).
   "Leave it on the branch" and "discard it" are first-class answers; pushing
   needs an explicit yes even when the apply phase was pre-authorized.

## Status & Apply-log format (canonical)

Every apply-capable lens report ends with the same two mechanics. The lens report
templates lay down the *skeleton* (the `Status:` line on each rec and an `## Apply
log` heading); this section is the single definition of what fills them, so the
templates point here instead of each restating it — if the vocabulary ever grows,
it grows in one place.

- **Status values** — each rec's `Status:` line moves through
  `pending` → `applied` | `failed (reverted)` | `skipped (not approved)`, where
  `applied` means the edit landed (or `applied (via <primary-id>)` for a
  subsumed rider whose Primary's single edit resolved it). The implementer
  edits only the `Status:` line of each rec it touches and appends to the
  Apply log; it changes nothing else in the report.
- **Apply-log lines** — the implementer appends one line per attempt under the
  report's `## Apply log` heading:
  - applied: `<UTC timestamp> [<rec-id>] applied — suite green (42 passed) — diffstat: 3 files, +120/-85`
  - reverted: `<UTC timestamp> [<rec-id>] FAILED — test_x broke, fix attempt failed, reverted`

Analyze-only reports (`ddd`, `clean-code`) have no apply phase, so `Status:
pending` there just records that a finding is unactioned and there is no Apply log.

## Guardrails

- **Behavior-preserving, always.** This workflow refactors; it does not
  redesign, add features, or "improve" logic. If a rec can't be done without
  changing behavior, it's High risk at minimum and probably belongs back with
  the human.
- **The report is the single source of truth.** Status changes and apply logs
  happen in the report file, not in ephemeral chat.
- **Judgment, not dogma.** Each lens's rubric lists when *not* to flag. A pass
  that atomizes a readable 200-line module into nine files has made the
  codebase worse. The goal is a human reader's comprehension, and every
  finding must argue its reader impact.
- **Never widen scope silently.** Unrelated problems noticed along the way go
  into the report's Reviewer notes or the final summary — not into the diff.
- **Fan-in at the orchestrator; artifacts always terminal.** Subagents never
  wait on a file a *peer* subagent is supposed to produce — you collect each
  agent's result and dispatch the next phase only once the previous phase's
  artifact exists and parses. Symmetrically, every agent's last act is writing
  its artifact *even when empty*: "no findings" is a written result, never an
  absent file. Then absence can only mean the agent died — record the coverage
  gap loudly and proceed. A silent stall is worse than a reported hole.
