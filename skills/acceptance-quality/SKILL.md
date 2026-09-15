---
name: acceptance-quality
description: >-
  Audit an existing ACCEPTANCE suite as a subject in its own right — the layer a
  human still reads, and the one none of the other six lenses grades.
  `test-quality` audits unit suites; this lens audits the scenarios above them:
  spec-as-spec (declarative Given/When/Then vs a click-by-click script),
  implementation leakage (selectors, table names, HTTP verbs where domain
  language belongs), domain coverage (acceptance criteria with no scenario,
  scenarios pinning no observable outcome), scenario coupling and
  order-dependence, step-definition DRY-ness (near-duplicate definitions, a
  vocabulary that only ever grows), PROSE CONSISTENCY (one term per concept, one
  tense per step keyword, one grammar for titles — the definitions are code and
  must be DRY, the scenario text is prose and must be consistent, which are
  different standards), and stale scenarios pinning behaviour that no longer
  exists. Audit-only, report-only: the BUILD path — writing specs and generating
  pipelines — stays with the `atdd` plugin and is never duplicated here, exactly
  as `/code-quality` uses `ddd` in analyze mode and never builds. Gherkin is the
  deepest-supported dialect, loaded as a reference rather than hardcoded, so
  another dialect is a file. Use for "/acceptance-quality", acceptance test
  review, Gherkin/Cucumber/BDD suite audit, feature-file smells, "are these
  scenarios any good", step-definition duplication, flaky or order-dependent
  acceptance suites.
user-invocable: true
metadata:
  version: "0.1.0"
  source: "The acceptance layer as the load-bearing human checkpoint"
---

# acceptance-quality — audit the layer a human occasionally reads

`test-quality` audits unit suites; this lens audits the scenarios above them. It was the
one layer no lens graded.

## Who reads this, and how

**Unit and integration suites are largely left to the agent.** Nobody reads a thousand
unit tests; they are written, run, and trusted because they are green. The acceptance
layer is different in one specific way: **a human reads it occasionally** — when
onboarding, when a stakeholder asks what the system actually does, when a scenario fails
and somebody has to decide whether the test or the behaviour is wrong.

Occasionally, and **cold**. That is the standard this whole rubric is calibrated to. The
reader does not have the code loaded, has not read the step definitions, and is not going
to. They may be the person who agreed the behaviour eighteen months ago, or someone who
has never seen this system. A scenario that only makes sense with the implementation open
has failed at the one job this layer has.

So the lens's severity weighting is not the same as a unit-test lens's:

- **A scenario a cold reader cannot understand is a Major finding at minimum**, even if
  it runs perfectly and covers real behaviour. Passing is not the bar here; being read is.
- **A mechanical smell that costs a cold reader nothing is Minor.** A slightly wide
  `Background`, an inconsistent tense, a long `Examples` table — real, small, and not
  worth an argument with the people who wrote them.
- **The absence of a scenario for agreed behaviour outranks the craft of the scenarios
  that exist.** A beautifully-written suite that does not say what the system does is the
  worse failure, and it is the one only this lens can see.

It is a guardrail, not a gauntlet: rigor scaled to how much a misunderstanding would
cost, not applied uniformly.

## The carve — audit here, build in `atdd`

The same split `/ddd` already makes between design mode and analyze mode:

- **`atdd` keeps the build path.** Generating specs, the spec IR, the test pipeline, and
  `spec-guardian`'s leakage check on specs being written. Unchanged, not duplicated.
- **This lens owns the audit path.** Grading an acceptance suite that already exists,
  with tiered findings, a decision gate and a guarded apply — the shared refactor
  workflow every other lens uses.

Where `atdd`'s `spec-guardian` rubric covers the same ground, **reuse it, don't
reimplement it**: cite it as the reference for what leakage is, and file the finding
here.

## Dialect, not language

Every other lens varies by *language*; this one varies by **dialect**. Gherkin is the
deepest-supported one and ships as [references/gherkin.md](references/gherkin.md); a
user-story-level WebDriver suite, a `describe`-based E2E suite or a plain-prose
acceptance doc is a different dialect and is added as a file, never by editing this
body — the same detect-and-load convention, one axis over.

This is deliberate. Gherkin's commercial track record is genuinely mixed, and hard-coding
it would inherit that bet. Detecting the dialect rather than assuming it costs nothing and
keeps the lens honest about suites that are acceptance tests without being `.feature`
files.

## Workflow

Follows [../../docs/refactor-workflow.md](../../docs/refactor-workflow.md) Phases 0–3;
apply (4–5) is opt-in and guarded. Analyzer drafts, an independent reviewer verifies and
tiers, the human decides.

**Report-only by default.** A scenario is a specification of agreed behaviour, so
rewriting one is a conversation, not a refactor: every change to a scenario's *meaning*
is a per-scenario human decision, never a batch apply. Mechanical changes (extracting a
duplicated step, renaming a step for consistency) go through the shared TDD refactor
engine with the acceptance suite green before and after.

## Absence is data

**No acceptance suite is an ordinary answer.** Most repos have none. Detect, record one
Coverage line, and cost nothing — do not invent scenarios, do not recommend adopting
Gherkin, and do not file "you have no acceptance tests" as a finding. Whether a project
should have an acceptance layer is a product decision this lens has no standing to make.

## Under the `code-quality` umbrella

Runs by default as the seventh lens, and auto-skips when Phase 0 finds no suite — which
is why it is not opt-in: a repo that *does* have acceptance specs never silently misses
the lens, and one that does not pays nothing.

## Overlaps — file once, at the owning altitude

Per [../../docs/lens-overlap.md](../../docs/lens-overlap.md): leakage of domain language
is `ddd`'s ubiquitous language at this altitude; duplicated step **definitions** are
`clean-code`'s DRY; the acceptance-vs-unit boundary is `test-quality`'s. Cross-reference,
never duplicate.

**Prose consistency is this lens's alone.** No other lens reads the scenario text as
prose, and the standard there is consistency rather than DRY-ness — a distinction worth
holding onto, because applying DRY to prose would merge away the very examples this layer
exists to give. Say the same thing the same way; do not say it once.
