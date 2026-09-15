---
name: clean-code
description: >-
  The repo's line-level craft standard (Robert C. Martin's Clean Code, read
  pragmatically) in two roles. As a SUBSTRATE it is the single source of truth
  every code-producing skill links, so written and refactored code is clean by
  construction. As a REVIEW it checks a diff, file, or PR for cleanliness on its
  own — naming, function/class design, error handling, comments, tests — with
  file:line locations and a severity. Use for "/clean-code", "review this", "is
  this clean", "any code smells", "tidy this up", "refactor suggestions", or when
  asked whether code is well-structured. Encodes judgment, not dogma: it says
  when a rule applies AND when applying it would make the code worse. Does NOT
  auto-rewrite a codebase unprompted, enforce a linter/formatter config, or
  replace security-review or /ship.
user-invocable: true
metadata:
  version: "0.3.0"
  source: "Robert C. Martin, Clean Code (2008), read pragmatically"
---

# clean-code — the craft substrate + standalone review

All the substance lives in **[../../docs/clean-code-standard.md](../../docs/clean-code-standard.md)** —
the single source of truth. This file is thin on purpose: it says how the standard
gets *used*.

## Two roles

- **Substrate (ambient).** The standard is linked by the shared implementer role
  ([../../docs/refactor-agents/implementer.md](../../docs/refactor-agents/implementer.md))
  and by `tdd` ([../tdd/references/refactor-jobs.md](../tdd/references/refactor-jobs.md)),
  so every `solid` / `gof` / `clean-architecture` refactor and every test-first
  line is clean **by construction**. You don't invoke anything for this — it is
  the house default for writing and editing code here.
- **Standalone review (invoked).** `/clean-code [scope]` reviews code for
  cleanliness with no other lens in play. `scope` is a path, a diff, or a
  range (default: the uncommitted working tree — this lens reviews a change,
  not a tree).

## Measure before you read

Run the probe's **chunk review** sink over the chunk first — it costs a
second and tells you where to look:

```bash
sh "$CLAUDE_PLUGIN_ROOT/bin/mente-python" "$CLAUDE_PLUGIN_ROOT/scripts/complexity_probe.py" --sink review <scope>
```

`<scope>` is a path, a diff, or a range (`OrderService.java:40-120`); bare means
the uncommitted working tree. **This never blocks** — it prints numbers and
hands them to your judgment. A high count is a place to look, not a finding: it
is only a finding once you can name the readability or changeability cost.

Where the probe cannot run — no probe for the language, tool absent — say so and
review unaided. Absence is data, never silence (`docs/status-vocabulary.md`).

## Review — two gears

Scale effort to scope. **Read the standard first**, then:

- **Quick (default for a diff or a few files).** One read-through against the
  standard; report findings inline (the *Suggested output* format in the
  standard). No subagents, no report file — the common case stays light.
- **Deep (a PR, a module, or on request).** Follows
  [../../docs/refactor-workflow.md](../../docs/refactor-workflow.md) Phases 0–2
  verbatim — including the structural-graph detection + verdict, the stale-draft
  pre-clear, and the git-exclude via `.git/info/exclude` for
  `docs/reports/clean-code/`: dispatch `agents/analyzer.md` (read-only over the
  code; writes `docs/reports/clean-code/draft-findings.md`) then
  `agents/reviewer.md` (re-verifies every finding against the code, prunes false
  positives, writing the report to
  `docs/reports/clean-code/CLEAN-CODE-REPORT-<YYYY-MM-DD>.md` per
  `references/report-template.md`); once it exists and parses, the orchestrator
  reaps the draft per the shared Phase 2.

## Non-overlap — defer up-ladder

clean-code owns line-level craft only. When a finding is really a **structural**
problem, name it and hand it up the altitude ladder rather than solving it here:

- responsibilities / dependency direction / the five principles → **`/solid`**
- a recurring object-collaboration that wants a pattern → **`/gof`**
- domain modelling (aggregates, ubiquitous language, ports) → **`/ddd`**
- the component/dependency graph, cycles, framework-as-detail → **`/clean-architecture`**

## Apply — opt-in only

This lens's own run stops at findings — Phases 0–2 plus the lens's own review gate/stop only; that constrains the run, not
the finding. Code-level nits are cheap to fix by hand and riskiest to mass-apply, so
apply only when the user asks — then reuse the shared implementer/TDD path
(`../../docs/refactor-workflow.md` Phases 4–5), which already cleans to this same
standard. That path applies rec IDs, so only a **deep**-gear report
(`references/report-template.md`) is applicable through the shared engine — the
**quick** gear's inline findings carry no rec ID to apply; rerun deep first if apply
is wanted.

## Guardrails

- **The standard is the single source of truth** — this skill and every consumer
  link `docs/clean-code-standard.md`; never restate or fork it.
- **Judgment, not dogma.** Honour every "Where this bends" note; a clean review is
  a few high-signal items, not a pile of style nits. If nothing meaningful is
  wrong, say so.
- **Read-only by default.** Surface and explain; don't rewrite unless asked.
