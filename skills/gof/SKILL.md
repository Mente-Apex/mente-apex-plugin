---
name: gof
description: >
  Gang of Four design-pattern analysis and guided refactor for Python codebases.
  Two-stage analysis: an analyzer detects existing patterns (graded A–F) and
  proposes where unimplemented patterns genuinely help; an independent reviewer
  verifies every finding, tiers the actionable ones (Critical/Major/Minor), and
  cross-references the SOLID lens. After human sign-off, approved changes are
  applied through the TDD refactor engine, one at a time, suite green after each.
  Use for "/gof", "what patterns are in my code?", "should I use a
  factory/observer/strategy here?", "is this a good Singleton?", pattern
  detection, or any mention of creational / structural / behavioral patterns.
user-invocable: true
metadata:
  version: "0.1.0"
---

# gof — GoF pattern analysis & guided refactor

GoF pattern analysis for Python codebases: detect and grade the design
patterns already implemented (A–F), propose genuine opportunities to apply
unimplemented patterns where they'd help, and — only after human sign-off —
apply approved recommendations through the shared TDD refactor engine, one
change at a time with the test suite as a tripwire.

**This skill follows [docs/refactor-workflow.md](../../docs/refactor-workflow.md).**
Its lens is `references/patterns.md` (rubric) + `references/report-template.md`.
Reports go to `docs/reports/gof/`. The HTML preview follows `references/html-report.md`.
Python idioms + test detection: `references/python.md`.

## Invocation

`/gof [path]` — `path` scopes the analysis (default: repo root). The user may
also pre-authorize in the same breath ("apply everything Critical", "doc
only", "don't ask, use light verification"). **Pre-authorizations count as
the human review for whatever they cover — don't re-ask.** This also makes
the skill usable non-interactively.

## Analyzer lens

The analyzer (`agents/analyzer.md`) runs two sub-passes against
`references/patterns.md`: **detect** — find patterns already implemented and
grade each one A–F against the rubric's Grade A / Grade C-D criteria — and
**opportunity** — locate genuine places an unimplemented pattern would help,
obeying that pattern's "Don't suggest when" clause. "No opportunity here"
(N/A) is a valid, trust-building outcome, not a coverage gap. Both sub-passes
feed the same draft findings file.

## Report

Per `references/report-template.md`, only the **Recommendations** section —
new-pattern opportunities plus low-grade detected patterns worth improving —
is apply-eligible; that's what the decision gate offers the human. The
**Detected patterns** graded inventory and the **Not applicable** table are
context: they explain the codebase's current pattern maturity but carry no
Status field and are never dispatched to the implementer. After the Markdown
report exists, the reviewer writes the HTML preview per
`references/html-report.md`.

## Interop with SOLID

The reviewer cross-references [docs/solid-gof-overlap.md](../../docs/solid-gof-overlap.md)
for every recommendation: findings that overlap the SOLID lens's territory
are noted with the shared principle/pattern, and where a SOLID report
already exists in `docs/reports/solid/`, its rec ID is cited instead of duplicating
the finding. The overlap map's one ⚠ entry — **Singleton vs. DIP** — is a
genuine tension between the two lenses, not a bug to resolve automatically:
surface it to the human at the decision gate and let them choose.

## Evolving this skill

The rubric lives in `references/patterns.md`, not this file. When the
human's gate decisions repeatedly disagree with the report — grades they'd
score differently, tiers or risks they consistently override — fold that
pattern back into `patterns.md` and bump this file's `metadata.version`.

## File map

- [references/patterns.md](references/patterns.md) — the 23-pattern rubric:
  detect signals, Grade A / Grade C-D criteria, Suggest/Don't-suggest
  triggers. Both analysis agents read it.
- [references/report-template.md](references/report-template.md) — the
  exact report shape (IDs, Risk, Status) the reviewer and implementer parse.
- [references/html-report.md](references/html-report.md) — the
  self-contained HTML preview spec, written after the Markdown report.
- [references/python.md](references/python.md) — idiomatic Python
  translations of the 23 patterns, plus test-suite detection.
- [agents/analyzer.md](agents/analyzer.md), [agents/reviewer.md](agents/reviewer.md),
  [agents/implementer.md](agents/implementer.md) — this skill's thin
  pointers into the shared roles.
- [../../docs/refactor-workflow.md](../../docs/refactor-workflow.md) — the
  shared Phase 0–5 orchestration this skill follows.
- [../../docs/refactor-agents/analyzer.md](../../docs/refactor-agents/analyzer.md),
  [../../docs/refactor-agents/reviewer.md](../../docs/refactor-agents/reviewer.md),
  [../../docs/refactor-agents/implementer.md](../../docs/refactor-agents/implementer.md) —
  the shared, lens-agnostic role instructions.
- [../../docs/solid-gof-overlap.md](../../docs/solid-gof-overlap.md) — the
  SOLID↔GoF overlap map used at review time.
