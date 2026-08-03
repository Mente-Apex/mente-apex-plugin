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
with a per-language `references/<language>.md` loaded for each language Phase 0
detects (the detect-and-load convention in the shared workflow). Reports go to
`docs/reports/solid/`.

## Invocation

Follows the shared Invocation contract exactly
([../../docs/refactor-workflow.md](../../docs/refactor-workflow.md#invocation))
rather than restating it: `/solid [scope]` — `scope` is a path, a diff, or a
range (default: repo root); pre-authorizations ("apply everything Critical",
"doc only", "don't ask, use light verification") count as the human review
for whatever they cover, including non-interactive use.

**Measure before you read.** Run the probe's **chunk review** sink first:
`sh "$CLAUDE_PLUGIN_ROOT/bin/mente-python" "$CLAUDE_PLUGIN_ROOT/scripts/complexity_probe.py" --sink review <scope>`
over the target. `<scope>` is a path, a diff, or a range
(`OrderService.java:40-120`). **This never blocks** — the numbers are triage,
pointing at where a type switch or a god class is likely to be. A finding still
has to name the design cost; a number alone is not one. Where the probe cannot
run, record it and analyze unaided
([../../docs/status-vocabulary.md](../../docs/status-vocabulary.md)).

## Apply, via TDD

Approved recommendations are applied **through the TDD refactor job**
([../tdd/references/refactor-jobs.md](../tdd/references/refactor-jobs.md)),
dispatched per [../../docs/refactor-workflow.md](../../docs/refactor-workflow.md)
Phase 4 — one rec (or dependent chain) at a time, suite green after each. What
used to be SOLID's own apply-phase choices — "characterization tests first"
vs. "light verification" vs. "stop at the doc" — are decided at the same
Phase 3 human gate and passed straight through as the refactor job's
`coverage` policy; this skill no longer implements the apply mechanics itself.

## Interop with the other lenses

The reviewer cross-references [../../docs/lens-overlap.md](../../docs/lens-overlap.md) for
every recommendation — GoF is the deepest overlap, but not the only one:

- **GoF** — findings that overlap GoF's territory are noted with the shared
  principle/pattern, and where a GoF report already exists in `docs/reports/gof/`,
  its rec ID is cited instead of duplicating the finding. The overlap map's one ⚠
  entry — **Singleton vs. DIP** — is a genuine tension between the two lenses, not
  a bug to resolve automatically: surface it to the human at the decision gate and
  let them choose.
- **clean-architecture** — a dependency-direction violation or an ADP cycle CA
  finds is one change shared with DIP, not two: whichever lens runs first files
  it; the other cites that rec ID rather than re-filing it.
- **test-quality** — an over-mocking finding ("this test can only run by mocking
  `X`") names a production DIP smell; SOLID files the fix (the missing seam),
  and test-quality's finding references that rec instead of standing alone.

Where a rec is better expressed in one of these lenses, mark it and recommend
that skill instead of filing it here.

## Guardrails

Follows the shared Guardrails exactly
([../../docs/refactor-workflow.md](../../docs/refactor-workflow.md#guardrails))
rather than restating them: behavior-preserving only, the report as the single
source of truth, judgment over dogma, never widen scope silently, and the
fan-in / artifacts-always-terminal rule for subagents. This skill's own
addition: `references/principles.md` carries the per-principle when-NOT-to-flag
rules — read it before pruning a finding as false-DRY or over-abstraction. A
SOLID pass that atomizes a readable 200-line module into nine files has made
the codebase worse; the goal is a human reader's comprehension, and every
finding must argue its reader impact.

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
- `references/<language>.md` — per-principle idioms and test-runner detection for
  a detected language; ships `python.md`, `typescript.md`, and `java.md` today
  (list the `references/` dir for the current set). New languages drop in here.
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
- [../../docs/lens-overlap.md](../../docs/lens-overlap.md) — the
  cross-lens overlap map used at review time (deepest with GoF, but also
  clean-architecture and test-quality).
