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
  version: "0.4.0"
---

# solid — SOLID analysis & guided refactor

AI-generated code usually *works* but often reads badly: god classes, type
switches copy-pasted across files, business logic that instantiates its own
database client. This skill uses the five SOLID principles as a lens to find
those problems, writes a **refactor plan a human can actually evaluate**, and
— only after human sign-off — applies it change by change through the shared
TDD refactor engine, one change at a time with the test suite as a tripwire.
The human is always the editor; the skill never redesigns on its own.

**This skill follows [../../docs/refactor-workflow.md](../../docs/refactor-workflow.md).**
Its lens is `references/principles.md` (rubric) + `references/report-template.md`,
with `references/python.md` / `references/typescript.md` for language
specifics. Reports go to `solid-reports/`.

## Invocation

`/solid [path]` — `path` scopes the analysis (default: repo root). The user may
also pre-authorize in the same breath ("apply everything Critical", "doc only",
"don't ask, use light verification"). **Pre-authorizations count as the human
review for whatever they cover — don't re-ask.** This also makes the skill
usable non-interactively.

## Apply, via TDD

Approved recommendations are applied **through the TDD refactor job**
(`skills/tdd/references/refactor-jobs.md`), dispatched per
`docs/refactor-workflow.md` Phase 4 — one rec (or dependent chain) at a time,
suite green after each. What used to be SOLID's own apply-phase choices —
"characterization tests first" vs. "light verification" vs. "stop at the
doc" — are decided at the same Phase 3 human gate and passed straight through
as the refactor job's `coverage` policy; this skill no longer implements the
apply mechanics itself.

## Interop with GoF

The reviewer cross-references
[../../docs/solid-gof-overlap.md](../../docs/solid-gof-overlap.md) for every
recommendation: findings that overlap the GoF lens's territory are noted with
the shared principle/pattern, and where a GoF report already exists in
`gof-reports/`, its rec ID is cited instead of duplicating the finding. The
overlap map's one ⚠ entry — **Singleton vs. DIP** — is a genuine tension
between the two lenses, not a bug to resolve automatically: surface it to the
human at the decision gate and let them choose.

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

- [references/principles.md](references/principles.md) — one-line canonical
  definitions (anchors, not teaching material) plus the parts that are NOT
  baked into any model: this skill's tier & risk rubrics, AI-code violation
  signatures, and per-principle when-not-to-flag rules. **Both analysis
  agents must read it** — they start with fresh context, and a shared rubric
  is what makes the generator–critic pair calibrated. Read it yourself before
  the decision gate.
- [references/python.md](references/python.md) /
  [references/typescript.md](references/typescript.md) — per-principle
  idioms and test-runner detection for the two deep-support languages.
- [references/report-template.md](references/report-template.md) — the exact
  report format.
- [agents/analyzer.md](agents/analyzer.md), [agents/reviewer.md](agents/reviewer.md),
  [agents/implementer.md](agents/implementer.md) — this skill's thin pointers
  into the shared roles.
- [../../docs/refactor-workflow.md](../../docs/refactor-workflow.md) — the
  shared Phase 0–5 orchestration this skill follows.
- [../../docs/refactor-agents/analyzer.md](../../docs/refactor-agents/analyzer.md),
  [../../docs/refactor-agents/reviewer.md](../../docs/refactor-agents/reviewer.md),
  [../../docs/refactor-agents/implementer.md](../../docs/refactor-agents/implementer.md) —
  the shared, lens-agnostic role instructions.
- [../../docs/solid-gof-overlap.md](../../docs/solid-gof-overlap.md) — the
  SOLID↔GoF overlap map used at review time.
