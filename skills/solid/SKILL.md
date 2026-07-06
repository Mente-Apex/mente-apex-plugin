---
name: solid
description: >
  Analyze a codebase against the five SOLID principles and produce a tiered
  refactor plan (Critical / Major / Minor), then — after human sign-off — apply
  approved recommendations one at a time, running the full test suite after
  every change. Two-stage analysis: an analyzer agent drafts findings and an
  independent reviewer verifies each one against the real code before the human
  reads anything. Built to make AI-generated codebases readable to humans. Use
  whenever the user says "/solid", "SOLID review", "SOLID audit", "check
  SOLID", mentions single responsibility, open/closed, Liskov substitution,
  interface segregation, or dependency inversion, complains about god classes,
  tangled architecture, or unreadable AI-generated code, or asks for an
  architecture-level refactor plan — even if they don't say the word "SOLID".
user-invocable: true
metadata:
  version: "0.3.0"
---

# solid — SOLID analysis & guided refactor

AI-generated code usually *works* but often reads badly: god classes, type
switches copy-pasted across files, business logic that instantiates its own
database client. This skill uses the five SOLID principles as a lens to find
those problems, writes a **refactor plan a human can actually evaluate**, and
— only with sign-off — applies it change by change with the test suite as a
tripwire. The human is always the editor; the skill never redesigns on its own.

**The cast** (you are the main agent / orchestrator):

| Role | Who | Instructions | Writes code? |
|------|-----|--------------|--------------|
| Orchestrator | you | this file | no |
| Analyzer | subagent | `agents/analyzer.md` | no (read-only) |
| Reviewer | subagent | `agents/reviewer.md` | no (writes only the report) |
| Implementer | subagent | `agents/implementer.md` | yes (approved recs only) |

All paths below are relative to this skill's directory. Dispatch subagents with
the Agent tool (`general-purpose`), telling each to read its instruction file
first. **If you cannot spawn subagents** (no Agent tool, or you are already a
subagent), play the roles yourself *sequentially and honestly*: finish the
analysis pass completely, then re-read the code fresh for the verification pass
before writing the final doc. The role separation is what keeps false positives
out of the report — don't collapse it.

## Invocation

`/solid [path]` — `path` scopes the analysis (default: repo root). The user may
also pre-authorize in the same breath ("apply everything Critical", "doc only",
"don't ask, use light verification"). **Pre-authorizations count as the human
review for whatever they cover — don't re-ask.** This also makes the skill
usable non-interactively.

## Phase 0 — Inventory & baseline

Before any agent runs, establish ground truth yourself:

1. **Scope**: list the target tree (skip vendored/generated dirs: node_modules,
   .venv, dist, build, migrations, *_pb2.py, lockfiles). Note languages, rough
   size, entry points.
2. **Test suite**: detect it and record the exact command (see the detection
   table in `references/python.md` / `references/typescript.md`; for other
   stacks use the project's README/CI config). Then **run it once**. The
   baseline matters: a failure after a refactor is only attributable if the
   suite was green before it.
   - Baseline green → proceed.
   - Baseline red → tell the user which tests already fail; the apply phase may
     still run but only those pre-existing failures are tolerated afterward.
   - No suite at all → note it; the decision gate (Phase 3) handles it.
3. **Report dir**: create `solid-reports/` in the target project and add it to
   the project's `.gitignore` if it's a git repo and not already ignored.

## Phase 1 — Analyzer

Spawn the analyzer with: the target path, the scope notes from Phase 0, and
instructions to read `agents/analyzer.md` plus `references/principles.md` (and
the matching language reference if Python or TypeScript). It produces
`solid-reports/findings-draft.md` — evidence-backed candidate findings, not yet
trusted.

## Phase 2 — Reviewer

Spawn the reviewer with the draft path and the same references. The reviewer
re-opens the actual code for **every** finding, prunes what doesn't hold up,
re-tiers what does, hunts for cross-file violations the analyzer's file-by-file
pass tends to miss, and writes the final report to
`solid-reports/SOLID-REFACTOR-<YYYY-MM-DD>.md` using
`references/report-template.md` **exactly** — the apply phase depends on its
structure (IDs, Risk and Status fields).

## Phase 3 — Decision gate (human)

Read the final report and present a compact summary: findings count by tier,
the top readability wins, and anything marked High risk. Then ask the user
(AskUserQuestion) which recommendations to apply — by tier ("all Critical +
Major") or by ID — unless they already pre-authorized. **"None — I just wanted
the doc" is a first-class outcome**, not a failure; stop there gracefully.

If the project has **no test suite** and the user wants changes applied, ask
how to proceed:

- **Stop at the doc** — safest, nothing is touched.
- **Characterization tests first** — the implementer writes tests pinning
  current behavior of the code each approved rec touches, *before* refactoring
  it. Slower, safest apply path.
- **Light verification** — no suite; after each change the implementer
  type-checks/compiles, imports every touched module, and smoke-runs the entry
  point. Make sure the user understands this catches breakage, not behavior
  drift.

## Phase 4 — Apply (tiered hybrid approval)

Split the approved recommendations by their **Risk** field:

- **Low/Medium risk** → dispatched to implementers as described below.
- **High risk** (public API signatures, cross-module moves, anything
  behavior-adjacent) → confirm **each one individually** with the user first:
  show the recommendation and the planned change, get a yes/no, then dispatch.
  A blanket pre-authorization that explicitly includes high-risk items ("apply
  everything, including high-risk") satisfies this.

**One implementer per rec** (or per dependent chain), dispatched
**sequentially**, each with a fresh context. One implementer grinding through
a long batch spends its shrinking context window on the later recs — the
widest change gets reasoned about in the dregs. Per-rec contexts also isolate
failure: a rec that reverts poisons nothing downstream, and blame stays 1:1.

Order the queue first: recs touching the same file form one **chain** (same
implementer, dependency order — a rec that moves code into a module another
rec creates runs after it); order chains Critical → Major → Minor. Give each
implementer: the report path, its rec ID (or chain), the test command and
baseline status, and the verification mode from Phase 3. It updates Status and
the Apply log in place and yields a structured summary — read it before
dispatching the next.

**Parallel option** — for large approvals (roughly 6+ recs across disjoint
files) independent chains may run concurrently, each in its own git worktree
(`isolation: worktree`). Two hard rules: recs touching the same file never run
in parallel, and per-worktree green proves nothing about the combination —
after merging, run the full suite once on the merged tree yourself. Merged
suite red → fall back to the sequential contract: revert the merge and re-land
chains one at a time until blame is attributable. Parallelism is an
optimization; sequential is the contract.

## Phase 5 — Final review & loop

When the implementer yields:

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

## Guardrails

- **Behavior-preserving, always.** This skill refactors; it does not redesign,
  add features, or "improve" logic. If a rec can't be done without changing
  behavior, it's High risk at minimum and probably belongs back with the human.
- **The report is the single source of truth.** Status changes and apply logs
  happen in the report file, not in ephemeral chat.
- **Judgment, not dogma.** `references/principles.md` lists for each principle
  when *not* to flag. A SOLID pass that atomizes a readable 200-line module
  into nine files has made the codebase worse. The goal is a human reader's
  comprehension, and every finding must argue its reader impact.
- **Never widen scope silently.** Unrelated problems noticed along the way go
  into the report's Reviewer notes or the final summary — not into the diff.
- **Fan-in at the orchestrator; artifacts always terminal.** Subagents never
  wait on a file a *peer* subagent is supposed to produce — you collect each
  agent's result and dispatch the next phase only once the previous phase's
  artifact exists and parses. Symmetrically, every agent's last act is writing
  its artifact *even when empty*: "no findings" is a written result, never an
  absent file. Then absence can only mean the agent died — record the coverage
  gap loudly and proceed. A silent stall is worse than a reported hole.

## Evolving this skill

The workflow above is fixed; the *judgment* is not. All calibration —
violation signatures, don't-flag rules, Scale calibration, the tier & risk
rubrics — lives in `references/principles.md` precisely so it can be tuned
without touching the orchestration. When the human's decisions at the gate
repeatedly disagree with the report — findings they wanted that were pruned,
tiers they always downgrade, risks that proved overstated — treat that as
rubric drift, not user error: offer to fold the pattern back into
`principles.md` (and bump the version in this file's frontmatter). One honest
rubric edit beats re-litigating the same judgment call every run.

## File map

- `references/principles.md` — one-line canonical definitions (anchors, not
  teaching material) plus the parts that are NOT baked into any model: this
  skill's tier & risk rubrics, AI-code violation signatures, and per-principle
  when-not-to-flag rules. **Both analysis agents must read it** — they start
  with fresh context, and a shared rubric is what makes the generator–critic
  pair calibrated. Read it yourself before the decision gate.
- `references/python.md` / `references/typescript.md` — per-principle idioms
  and test-runner detection for the two deep-support languages.
- `references/report-template.md` — the exact report format.
- `agents/analyzer.md`, `agents/reviewer.md`, `agents/implementer.md` — role
  instructions for the three subagents.
