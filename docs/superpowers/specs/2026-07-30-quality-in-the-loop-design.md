# Quality in the loop — design

**Status: DRAFT — brainstorming partly resolved.** This is a snapshot of an
unfinished conversation, not a plan to execute. The *Settled* section is stable
enough to build from; the *Open questions* and *Unexplored threads* sections are
the actual point of the document. Do not implement past a question that is still
open in §5.

**Update 2026-08-02:** §5.1 and §5.2 are resolved in
[`2026-08-02-cycle-gate-verdict-design.md`](2026-08-02-cycle-gate-verdict-design.md),
which unblocks **#117, #124, #118** and absorbs **#121**. Still open: §5.3, §5.4,
§5.5, §5.6, and all of §6.

Origin: research pass over Robert C. Martin's July 2026 "I don't read AI-written
code" position (`docs/Uncle_Bob_AI_Publications_Overview.docx` plus primary
sources), which surfaced a set of gaps in the toolkit — and then a sharper,
independent critique of the toolkit's *shape* that reframed all of them.

---

## 1. Problem

Two findings, the second more important than the first.

### 1.1 The gauntlet gap (what the research found)

Martin replaces code review with five measured sensors: **test coverage,
dependency structure, cyclomatic complexity, module sizes, mutation testing**
([tweet 2044114698451476492](https://x.com/unclebobmartin/status/2044114698451476492)),
plus two human-reviewed artifact layers (Gherkin acceptance tests, QA
procedures) with rigor scaled to criticality.

Audited against the six lenses:

| Sensor | Status |
|---|---|
| Dependency structure | **Exceeds it** — `clean-architecture`: grimp/madge, ADP/SDP, CI tripwire |
| Mutation testing | Present, but diff-scoped as an apply gate |
| Test coverage | Present, but inverted — only the stale-test deletion gate |
| Cyclomatic complexity | **Absent** — zero hits for cyclomatic/radon/lizard/CRAP across `skills/`, `docs/`, `scripts/` |
| Module size | Absent as a signal — Phase 0 records rough LOC, nothing consumes it |
| Acceptance layer | No lens. `test-quality` audits unit suites only |

### 1.2 The shape problem (the real one)

`/code-quality` is post-factum corrective analysis, not part of development.
Two distinct halves, and neither is what it first looks like:

**Design is reachable but never routed to.** `/ddd` DESIGN mode gates the model
and then drives `/tdd` to build innermost-out (`skills/ddd/SKILL.md:96`). But
`/tdd` never asks whether there is a domain to design first — DDD appears in
`skills/tdd/SKILL.md` only at line 232, as *testing* guidance for hexagonal
projects. And `/tdd` owns the wide trigger surface ("implement", "build",
"create", "add feature"). **The default path from "build me X" to code bypasses
design entirely.**

**The in-loop checks and the mechanical checks are inverted.** TDD's REFACTOR
step *is* in-loop and mandatory (`skills/tdd/SKILL.md:156-177`), covering names,
one-thing functions, duplication, nesting, responsibility drift, dependency
direction, mocking-as-design-signal. But every check is prose evaluated by agent
judgment — "nesting stays shallow" with no number. The skill concedes the
failure mode itself:

> *"Evaluate every cycle, even when the outcome is 'nothing to refactor' — say
> so explicitly. **Silence is how this step evaporates.**"*

A guard needing a nag to survive is not a guard. Meanwhile every mechanical
check the toolkit owns runs only inside an audit. So: **in-loop checks are
advisory prose; mechanical checks are post-factum.** Both backwards.

Corroborating: the plugin ships one hook, `merged_branch.py` (branch hygiene).
The clean-code substrate reaches `tdd/references/refactor-jobs.md` and the
refactor implementer — the refactor engine, only ever invoked *from an audit*.
It never reaches a fresh feature build.

---

## 2. Frame: the frequency ladder

Each tier runs only what it can afford. This is the organizing idea.

| Tier | When | Cost | Runs | Status |
|---|---|---|---|---|
| Write-time | per edit | free | substrate prose | exists, advisory-only |
| **Cycle-gate** | per green cycle | seconds | mechanical checks, changed functions only | **missing** |
| Change-gate | per branch | ~1 min | diff-scoped lens pass, cycles, changed-line coverage, mutation-on-diff | partial |
| Audit | on demand | minutes | the six-lens umbrella | exists |

**Correction 2026-08-02 — the ladder is not language-neutral.** This table was
written as if every tier is available in every language. It is not: Java's
structural tooling (`jdeps`, ArchUnit, PIT) reads **bytecode**, so it cannot run
at cycle frequency at all, and sits at the change-gate rung instead. Which
probes are affordable at which rung is per-language data. See
[`2026-08-02-cycle-gate-verdict-design.md`](2026-08-02-cycle-gate-verdict-design.md)
§3 and §5.

**What cannot move in-loop, and must not be forced to:** an anemic domain
model, an import cycle, a god class, an LSP violation. These only have answers
once code exists at scale. Running DDD analysis per-edit is a category error.
The design half (§1.2) addresses this not by moving the *audit* earlier but by
moving the *decision* earlier — before the model exists.

---

## 3. Settled

Filed as issues; the reasoning is stable.

| # | Change | Note |
|---|---|---|
| [#117](https://github.com/menteapex/mente-apex-plugin/issues/117) | Phase 0 Measurements artifact (lizard CC, module size, coverage) | **Load-bearing** — see §4 |
| [#118](https://github.com/menteapex/mente-apex-plugin/issues/118) | `## Measurements` report section + before→after deltas | Turns apply-phase proof from "suite green" into measured effect |
| [#119](https://github.com/menteapex/mente-apex-plugin/issues/119) | Mutation score as a standing sensor (`--scope full`) | `--scope full` already exists; needs aggregation + opt-in flag |
| [#120](https://github.com/menteapex/mente-apex-plugin/issues/120) | Criticality-scaled audit depth | Low priority |
| [#121](https://github.com/menteapex/mente-apex-plugin/issues/121) | `unverified` status in Coverage & method | Cheap; makes an existing guardrail checkable |
| [#122](https://github.com/menteapex/mente-apex-plugin/issues/122) | Seventh lens: audit the acceptance layer | Two open calls — see §5.5 |
| [#123](https://github.com/menteapex/mente-apex-plugin/issues/123) | `/tdd` routes to `/ddd` design mode before first test | The design half |
| [#124](https://github.com/menteapex/mente-apex-plugin/issues/124) | Make in-loop checks mechanical | The vigilance half |

### 3.1 The governing ruling on metrics

Resolves a genuine conflict. `docs/clean-code-standard.md:41-48` deliberately
**rejects** mechanical size limits, and rejects Martin's own "extract till you
drop": *"Prefer 'can I read this in one pass?' over 'how few lines per
function?'"* Martin-2026 says the opposite — he *"constrains the hell out of"*
size and complexity, mechanically.

Both are right in context. The standard optimizes for **a human reading a
report**, where CC=14 is a question, not a defect, and auto-filing it is noise.
Martin optimizes for **nobody reading anything**, where metrics are the only
sensor left.

> **The ruling: a threshold breach is a place to look, never a finding on its
> own. A filed finding must still name the readability or changeability cost.**

Metrics are triage inputs to the analyzers. A CC of 22 doesn't get filed — it
tells `/solid` where to look for the type-switch, and turns a hunch into a
measured claim once found.

**Note this ruling was written for the audit tier and has not been re-examined
for the gate tier.** See §5.1 — it may not survive contact with a gate that
must return a binary verdict.

### 3.2 Positioning

`/code-quality` is the **complement** to the gauntlet, not a competitor.
Martin's five sensors are structurally blind to an anemic domain model, a wrong
abstraction from false DRY, a missing Strategy, an LSP violation, a boundary
leaking the ORM into the core. Five of six lenses detect exactly what those
metrics cannot see. The gauntlet answers *does it work?*; the lenses answer *is
it built well?*

### 3.3 Explicitly not adopted

- **"Don't read the code"** — would negate the toolkit. Booch's objection
  (metrics miss what pattern recognition catches) is the plugin's premise.
- **"TDD micro-steps are inefficient for AIs"** — his context is an agent's
  greenfield inner loop; ours is a refactor engine mutating tested code, where
  the micro-step *is* the safety proof.
- **AkitaOnRails's comment inversion** ("don't prune agent-written comments") —
  `clean-code-standard.md:97-106` already holds the more nuanced position.

---

## 4. The keystone: #117 has two consumers

#117 was filed as a **report input**. It is also the **engine for the cycle-gate**.
Same `lizard` run, two consumers — the audit's Measurements section (#118) and
the in-loop gate (#124). Build it once, feed both.

This is why #117 is the load-bearing issue of the set, and why #118 and #124
should not be designed independently of each other.

---

## 5. Open questions

**These are the reason this document is a draft.**

### 5.1 What does a gate do on breach? — **RESOLVED 2026-08-02**

**Settled in [`2026-08-02-cycle-gate-verdict-design.md`](2026-08-02-cycle-gate-verdict-design.md).**
The ruling: *the gate does not return a verdict on the code, it returns a
verdict on whether the check ran.* Produce a measurement or state why there
isn't one; **silence is the only thing that blocks**. §3.1's ruling survives
intact, because the gate never rules on content. Blocking is safe because a
block on process is never wrong and so never trains an override reflex.
Scope split: gates are for agent-written code, humans get feedback.

The original framing is kept below for the record.

Three options were considered, each with a real failure mode:

- **Block** (deny the tool call) — a CC>15 block will fire on legitimate code
  and train you to reflexively override, which destroys the signal.
- **Warn** — a gate that only warns is prose with extra steps: the exact
  failure mode §1.2 exists to fix.
- **Annotate** (record the breach, surface it at the next natural boundary) —
  weaker per-edit, but survives without training override reflexes.

Unresolved, and §3.1's ruling ("a breach is a place to look, never a finding")
was written for the audit tier. A gate has to return a verdict. Whether the
ruling extends, bends, or breaks here is genuinely open.

### 5.2 Who sets thresholds, and where? — **RESOLVED 2026-08-02**

**Settled in [`2026-08-02-cycle-gate-verdict-design.md`](2026-08-02-cycle-gate-verdict-design.md) §4.2.**
Off the critical path once §5.1 is settled: the gate blocks on silence, not on
breach, so an unconfigured project still has a working gate. Where a repo
already declares limits (Checkstyle/PMD/Sonar, ruff `mccabe`, ESLint
`complexity`), read them; where it declares none, report the distribution and
assert nothing. **The plugin ships no default numbers.**

The original framing is kept below for the record.

`clean-code-standard.md` rejects universal numbers on principle. So thresholds
must be per-project — but an unconfigured project then has no gate, which is
most projects. Defaults-with-override? What defaults, justified how? Does a
threshold live in the target repo or the plugin?

### 5.3 QA procedures — entirely unexamined

Martin's gauntlet has **two** human-reviewed artifact layers. We designed a lens
for the acceptance layer (#122) and never once looked at the second. Is there a
lens there? Is it out of scope for a code-quality toolkit? Not yet asked.

### 5.4 Does the umbrella shrink?

If the mechanical sensors run continuously in-loop, `/code-quality` may not need
to be a 6→7-lens fan-out. It might become the **judgment-only** lenses, with
metrics arriving pre-computed from the gate's history rather than re-measured
per audit. That would make the umbrella smaller, faster, and more clearly
purposed. Speculative; worth an hour.

### 5.5 The two calls made unilaterally in #122

- Generic "acceptance layer" with Gherkin as first dialect, vs Gherkin-specific.
  (Hedges Zhan's critique that Gherkin E2E has a poor commercial track record.)
- Default-on with auto-skip when no suite is detected, vs opt-in.

### 5.6 What counts as "there's a domain here"?

#123's triage question needs criteria cheap enough to answer in one judgment.
"Entities with identity and lifecycle, invariants, domain language, more than
CRUD" is a first sketch, not a rule.

---

## 6. Unexplored threads

Named so they are not lost. None has been thought through.

- **A gauntlet that learns.** Martin's is static. If the audit tier keeps
  finding the same class of smell, should that promote into a gate rule
  automatically? A feedback loop from audit → gate is a materially different
  and more interesting system than either tier alone. Nothing here explores it.
- **Where the standard lives.** The SOLID engineering standard is injected via a
  `UserPromptSubmit` hook in global config — outside this plugin. #124 proposes
  folding it in, but the general question (which standards travel with the
  toolkit vs the machine) is unaddressed.
- **Interaction with `engineer`'s DAE pipeline.** `engineer:refine` and
  `engineer:arch-check` already occupy the change-gate tier, wired to a charter
  rather than these lenses. Currently out of scope (single-user tooling), but it
  is duplication that will eventually need a carve.

---

## 7. Scope

Single-user tooling. No portability carve against the `engineer` plugin, no
design for standalone `/tdd` consumers.

## 8. Provenance caveat

X blocks direct fetching; the two Martin quotes are search-snippet
reconstructions, consistent across three independent secondary sources. Treat
content as reliable, dates as approximate. The source `.docx` missed the metrics
tweet entirely and flagged the primary tweet as unretrievable — both were
recoverable.
