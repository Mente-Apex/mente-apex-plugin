# Shared refactor workflow (Phase 0–5)

Shared orchestration for the plugin's refactor lenses (`solid`, `gof`,
`clean-architecture`, `test-quality`, and the `code-quality` umbrella that fans them out;
the analyze-only lenses `ddd` and `clean-code` use Phases 0–3 in their own run — their
findings' applicability is a property of the report fields, not the lens, so a finding
merged by the umbrella or opted into directly is applicable through the shared engine).
`test-quality` applies through this engine too but adds its own two safety gates on top —
a mutation gate for test refactors, a coverage-non-regression gate for deletions — since
"suite still green" cannot vouch for a changed or deleted test. Each
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
| Analyzer | subagent | `docs/refactor-agents/analyzer.md` | no (writes only the draft) |
| Reviewer | subagent | `docs/refactor-agents/reviewer.md` | no (writes only the report) |
| Implementer / TDD-coordinator | subagent | `docs/refactor-agents/implementer.md` | yes (approved recs only, via a TDD refactor job) |

All agent instruction paths above are relative to the plugin root. Dispatch
subagents with the Agent tool (`general-purpose`), telling each to read its
instruction file first. **Every role here writes its own artifact, so every
role needs `Write`** — the analyzer's "no" in the table above means *it does
not touch the code under audit*, not that it cannot write its draft.

> **Never name a subagent's artifact `REPORT*`, `SUMMARY*`, `FINDINGS*`, or
> `ANALYSIS*`.** Claude Code's `Write` tool hard-denies any subagent write
> whose **basename** starts with one of those four words (case-insensitive,
> `.md` only), returning a denial that reads like a blanket policy against
> subagents writing reports at all. **It is not one** — it is a filename check
> and nothing else: not a permission, not a hook, unaffected by
> foreground/background or agent type, and with no ask-the-user path. Read
> that denial as "rename the file", never as a licence to return the draft in
> chat; a blocked agent that falls back to chat re-emits the whole draft
> through the orchestrator's context, which is exactly the cost the subagent
> split exists to avoid.
>
> This is why the hand-off is `draft-findings.md` and **not** the reverse
> word order (issue #112). The dated `<LENS>-REPORT-<date>.md` is safe because
> its basename starts with the lens name, not `REPORT`. Any new agent-written
> artifact must clear the same check — put a distinguishing word first.

**If you cannot spawn subagents** (no Agent tool, or
you are already a subagent), play the roles yourself *sequentially and
honestly*: finish the analysis pass completely, then re-read the code fresh
for the verification pass before writing the final doc. The role separation
is what keeps false positives out of the report — don't collapse it.

**The draft is transient.** `draft-findings.md` is the analyzer→reviewer
hand-off, not a deliverable: **written** by the analyzer (Phase 1), **consumed**
by the reviewer (Phase 2), **deleted** by the orchestrator once the report is
durable (end of Phase 2). Only the dated `<LENS>-REPORT-<YYYY-MM-DD>.md`
persists. An edit that leaves the draft on disk between runs reintroduces the
stale-collision bug this rule exists to prevent.

## Invocation

`/<lens> [path]` — `path` scopes the analysis (default: repo root). The user
may also pre-authorize in the same breath ("apply everything Critical", "doc
only", "don't ask, use light verification"). **Pre-authorizations count as
the human review for whatever they cover — don't re-ask.** This also makes
the workflow usable non-interactively.

## Phase 0 — Inventory & baseline

Before any agent runs, establish ground truth yourself:

1. **Scope**: list the target tree (skip vendored/generated dirs: node_modules,
   .venv, dist, build, migrations, *_pb2.py, lockfiles). Note rough size and
   entry points, and record the **detected language set** — this drives which
   language reference each later phase loads (see the convention below).
   - **Detect a structural graph** while you are here, and pass the verdict to
     every later phase: does the target carry a `graphify-out/graph.json`, and
     is it current? See [docs/structural-queries.md](structural-queries.md) for
     the check, the freshness rule, and what to do when there is none — which is
     the common case and costs the run nothing but a Coverage line.
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
   - **Pre-clear a stale draft.** A `draft-findings.md` is a transient
     analyzer→reviewer hand-off, never a durable record, so a copy left in the
     report dir can only be stale — from a prior run that crashed between Phase 1
     and the end of Phase 2. Delete any pre-existing
     `docs/reports/<lens>/draft-findings.md` now, before Phase 1 writes. Dated
     final reports are the durable record and are left untouched.

### Language references — the detect-and-load convention

Lenses stay **language-agnostic in the body**; every language specific lives in a
reference file, and Phase 0's detected-language set decides which ones load. This
is the Open/Closed seam of the toolkit: **adding a language is adding a file, never
editing a SKILL body.**

- **Analysis lenses** load `references/<language>.md` (e.g. `python.md`,
  `typescript.md`) for each detected language — per-principle/per-pattern idioms,
  tool detection, and test-suite discovery.
- **The apply engine** (`tdd`) loads `references/<language>-<runner>.md` (e.g.
  `python-pytest.md`, `typescript-vitest.md`), keyed on the detected test runner.
- **No matching reference → degrade gracefully**: apply the language-agnostic
  rubric/cycle, discover test conventions from the repo, and note in the report
  that idiom-specific guidance wasn't available (an adapter could be added next
  time). Absence is a recorded coverage note, never a silent gap.

To see which languages a lens currently ships deep support for, list its
`references/` directory — don't rely on a hard-coded list in prose.

## Phase 1 — Analyzer

Spawn the analyzer with: the target path, the scope notes from Phase 0 (including
the detected-language set **and the structural-graph verdict**), and instructions
to read `docs/refactor-agents/analyzer.md`
plus the lens's rubric (`references/<rubric>.md`) and — per the detect-and-load
convention above — `references/<language>.md` for each detected language that has
one. It produces `docs/reports/<lens>/draft-findings.md` — evidence-backed
candidate findings, not yet trusted.

## Phase 2 — Reviewer

Spawn the reviewer with the draft path, the same references, **and the
structural-graph verdict**. The reviewer
re-opens the actual code for **every** finding, prunes what doesn't hold up,
re-tiers what does, hunts for cross-file violations the analyzer's
file-by-file pass tends to miss, and **cross-references the other lens** —
check [docs/lens-overlap.md](lens-overlap.md) for findings that overlap or conflict with
the sibling lens's territory so the two reports don't contradict each other —
before writing the final report to `docs/reports/<lens>/<LENS>-REPORT-<YYYY-MM-DD>.md`
using the lens's `references/report-template.md` **exactly**: the apply
phase depends on its structure (IDs, Risk and Status fields).

**Reap the draft.** Once you have confirmed the report exists and parses (the
fan-in in Guardrails), delete `docs/reports/<lens>/draft-findings.md` — its only
consumer is the reviewer, and from Phase 3 on the dated report is the single
source of truth. **Delete only against a parseable report:** if the reviewer
produced none (it died), keep the draft as the sole evidence of the partial run
and record the coverage gap per the "artifacts always terminal" guardrail — never
delete a draft you cannot replace with a report.

## Phase 3 — Decision gate (human)

Read the final report and present a compact summary: findings count by tier,
the top wins, and anything marked High risk. Then ask the user (AskUserQuestion)
which recommendations to apply — unless they already pre-authorized. **"None — I
just wanted the doc" is a first-class outcome**, not a failure; stop there gracefully.

**Resolve conflicts before computing the apply order.** If the report has a
`## Conflicts` section, each entry is a **fork** — two mutually-exclusive recs
where applying one voids the other. Resolve **every** conflict here, before any
ordering, with an explicit either/or (AskUserQuestion: pick the winner, or
"neither"). A mutual exclusion is a *branch, not a dependency* — the
dependency-aware apply order cannot be linearized while both sides are approved,
so resolution is upstream of Phase 4, not inside it. **Tier/blanket approval
cannot resolve a fork:** "apply all Major" is undefined over a mutually-exclusive
pair — intercept and force the pick **even under a pre-authorization** (a pre-auth
covers independent recs; a fork has no "all" answer). Record the loser's
`Status:` as `skipped (lost conflict to <winner-id>)` — not a bare
`skipped (not approved)` — so a later reader sees *why* it was excluded and does
not resurrect it. **Checklist: every declared conflict is resolved before the
apply order is computed.**

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

**A conflict must never reach here unresolved.** If a `## Conflicts` entry
somehow arrives at apply with no gate resolution, **halt and return to Phase 3** —
the implementer never picks a conflict's winner itself. (Phase 3's checklist
exists to prevent this; this is the backstop.)

**The Phase-0 shared index is analysis-only.** It was built once over the
read-only analysis snapshot; the apply phase mutates the tree via checkpoint
commits, so each implementer re-derives structural facts **fresh, per job**
against the live tree — never from that index. See
[docs/refactor-agents/implementer.md](refactor-agents/implementer.md).

Split the approved recommendations by their **Risk** field:

- **Low/Medium risk** → dispatched as described below.
- **High risk** (public API signatures, cross-module moves, anything
  behavior-adjacent) → confirm **each one individually** with the user first:
  show the recommendation and the planned change, get a yes/no, then dispatch.
  A blanket pre-authorization that explicitly includes high-risk items ("apply
  everything, including high-risk") satisfies this.

**Match the implementer's model to the job (token frugality).** A dead-parameter
deletion and a 23-module-cycle break are not the same amount of thinking, so don't
spend the same model on both. Dispatch each refactor job's implementer subagent
(Agent tool `model` override) keyed on the job's **Risk** — the signal you already
have:

- **Low** → `haiku` — mechanical, well-covered edits (drop dead code, hoist an
  import, name a constant, a single-site DRY extraction, a parameter object).
- **Medium** → `sonnet`.
- **High** → `opus` (or inherit the orchestrator's model) — cross-module moves,
  signature changes, anything behavior-adjacent that also passes the per-item gate.
- **Floor:** never below `sonnet` for a job whose targets need characterization pins
  first (`coverage: none`) — writing faithful pins that pin *exact* current behavior
  is delicate, and a weak pin is worse than none. Bump a job up a tier on judgment
  (a "Low" that touches a subtle invariant); the mapping is a default, not a cage.
  A group's tier/risk for this purpose is its **Primary's**.

**Each approved rec is applied by dispatching a TDD refactor job** — the
shared engine at
[skills/tdd/references/refactor-jobs.md](../skills/tdd/references/refactor-jobs.md).

**Dispatch rule for the implementer role:** dispatch the owning lens's
`agents/implementer.md` when the lens ships one; otherwise the shared `docs/refactor-agents/implementer.md`.
This holds for every caller, including
the `code-quality` umbrella fanning a rec back out to its lens of origin — a
`test-quality` rec always runs through `skills/test-quality/agents/implementer.md`,
never silently through the shared implementer, so its mutation gate and
coverage-non-regression gate stay wired regardless of which caller dispatched
it. The model-tiering above is orthogonal to this dispatch: the model still
varies by the job's Risk, independent of which implementer file is running.

Whichever file the rule selects, that implementer/TDD-coordinator role
translates a rec into that engine's calling contract (`targets`, `change`,
`test_command` + `baseline_status`, `coverage`) and then **runs** that
procedure itself — it is a subagent, so it writes the edits in its own
context rather than delegating further — as **one job
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

**Verification inside a group job.** Run the safety net after the **Primary + subsumed**
edit — green lands the core fix as one unit. Then apply each approved separable rider and
verify it; a separable edit that breaks the net **reverts alone**, leaving the Primary
green (an optional adjacent cleanup must never sink the core structural fix). The
refactor job updates Status and the Apply log in place and yields a structured summary
(`job_id`, `outcome`, `tests_written`, `coverage_proof`, `files_touched`, `diffstat`,
`suite_status`, `noticed_not_touched`) — read it before dispatching the next.

**Two-tier testing (so a big suite doesn't dominate wall time).** On a large suite,
running all of it after the Primary *and* after every rider is the main cost of a slow
apply. The refactor job may instead run a **scoped subset** (the tests exercising the
changed modules) for those *inner* checks, and the **full `test_command` once as the
job's end gate** — the mechanics are in the language adapter
([skills/tdd/references/refactor-jobs.md](../skills/tdd/references/refactor-jobs.md)).
Safety is preserved because the full run still precedes the checkpoint below: a
distant breakage is caught before the job is ever committed, just localized at
job-end rather than paid for on every rider.

**Checkpoint after each job (so the next agent sees an unambiguous baseline).** Each
implementer runs in a *fresh* context; if the tree still carries the uncommitted
diffs of jobs 1…N-1, job N can't tell the baseline from prior work and its own
diffstat is polluted — the "agents get confused between runs" failure. So once a job
yields `applied` **and you have independently confirmed the full suite is green**
(Phase 5, step 1, done per-job here), make a **checkpoint commit on the working
branch** — `refactor(<lens>): <group/rec id> — <one line>` — *before* dispatching the
next job. The next implementer then opens a clean tree whose only diff is its own.
These are working-branch checkpoints, not publication (see
[docs/git-convention.md](git-convention.md)); `/ship` squashes/curates them at the
end. A job that fails and reverts leaves nothing to checkpoint — the tree is already
back at the last green commit, exactly the clean baseline the next job needs.

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
4. **Summarize — into the report, not just chat.** Write the run's synthesis into the
   report's **`## Outcome`** section: what was applied (rec/group ids + net diffstat),
   what was deferred or not approved, what failed and why, suite status before/after,
   the *verification method* per job (existing-suite coverage vs. characterization pins
   written red-first — carried from each yield's `coverage_proof`), the number of
   checkpoint commits, and what remains for a future pass. The per-finding `Status:`
   lines and the Apply log are the raw ledger; the Outcome is the synthesis that must
   **survive loss of this session's context** — a chat-only summary is gone the moment
   the window rolls, which is precisely the overview a returning session most needs.
   Then also say it in chat. (If the report has no `## Outcome` heading — an older
   template — add one; if nothing was applied, there is no Outcome to write.)
5. **Offer to commit and PR — never auto-publish.** Per the git convention,
   propose a Conventional Commit for the working branch and ask whether to
   commit and raise a PR (the plugin's `/ship` skill is exactly that flow).
   "Leave it on the branch" and "discard it" are first-class answers; pushing
   needs an explicit yes even when the apply phase was pre-authorized.

## Status, Apply-log & Outcome format (canonical)

Every apply-capable report ends with the same mechanics. The report templates lay down
the *skeleton* (the `Status:` line on each rec, an `## Apply log` heading, and — where
present — an `## Outcome` heading); this section is the single definition of what fills
them, so the templates point here instead of each restating it — if the vocabulary ever
grows, it grows in one place. The finding *shape* itself — the field set, the ID/anchor/
filename rules, and the lens-flavoured field aliases — is defined once in
[report-contract.md](report-contract.md), not here.

- **Status values** — each rec's `Status:` line moves through
  `pending` → `applied` | `failed (reverted)` | `skipped (not approved)` |
  `skipped (lost conflict to <winner-id>)`, where
  `applied` means the edit landed (or `applied (via <primary-id>)` for a
  subsumed rider whose Primary's single edit resolved it), and
  `skipped (lost conflict to <winner-id>)` is the loser of a Phase-3 conflict
  fork (distinct from `skipped (not approved)` so a later reader sees *why* it
  was excluded). The implementer
  edits only the `Status:` line of each rec it touches and appends to the
  Apply log; it changes nothing else in the report.
- **Apply-log lines** — the implementer appends one line per attempt under the
  report's `## Apply log` heading. Each carries a **safety clause** — the coverage
  source, or the pins written red-first — because that clause is what makes "a safe
  refactor actually ran through the engine" observable after the fact, rather than
  taken on faith:
  - applied (covered): `<UTC ts> [<rec-id>] applied — covered by test_x.py::… — suite green (42 passed) — diffstat: 3 files, +120/-85`
  - applied (was uncovered): `<UTC ts> [<rec-id>] applied — uncovered → N pins written red-first (test_x.py) — suite green (45 passed) — diffstat: 2 files, +80/-30`
  - subsumed rider: `<UTC ts> [<rider-id>] applied — subsumed by <primary-id> (no separate edit)`
  - reverted: `<UTC ts> [<rec-id>] FAILED — test_x broke, fix attempt failed, reverted`
- **Outcome** — where the template has an `## Outcome` heading, the orchestrator (not
  the implementer) fills it once at Phase 5 as the persisted run synthesis: applied /
  deferred / failed ids, baseline → final suite status, net diffstat, checkpoint count,
  the aggregate verification method (covered vs. pins-first), and residuals for a next
  pass. It exists so the result outlives this session's context — see Phase 5, step 4.
  Omit it on an audit-only run.

If a report has an `## Outcome` heading but predates the coverage-source apply-log
clause, keep appending in the newer form — the older lines stay valid; the vocabulary
only ever grows.

Analyze-only lenses' own runs (`ddd`, `clean-code`) never reach Phase 4–5, so `Status:
pending` there just records that a finding is unactioned by this run — that constrains
the run, not the finding: once merged by the umbrella or opted into directly, the same
finding is applicable through the shared engine and gets an Apply-log line like any
other rec.

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
