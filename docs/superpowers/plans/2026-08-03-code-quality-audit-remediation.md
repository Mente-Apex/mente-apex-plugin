# Code-quality umbrella & lens remediation — plan (audit of 2026-08-03)

Source: full audit of the `code-quality` umbrella, its six lenses, and the shared
engine docs. Suite was green at audit time (1144 passed); every finding below is a
prose-contract defect the tests do not cover. Findings are grouped into workstreams
ordered by risk; each item carries its location and an acceptance criterion.

**Design stance (DIP, applied to the docs themselves):** the recurring root cause is
concretions where abstractions should be — six templates each hand-rolling the finding
schema, Phase 4 hard-wired to one concrete implementer, role docs restating (and
drifting from) the contract. The fixes below therefore centre on two abstractions:
a single **canonical finding schema** every template references instead of restates
(WS-1), and a **lens-implementer resolution rule** Phase 4 depends on instead of one
concrete role file (WS-2). Everything else is a sweep to realign prose with those.

---

## Decisions required before implementation (gate these with the human)

- **D1 — What does "analyze-only" mean?** Recommended: *analyze-only constrains the
  lens's own run, not its findings.* A ddd/clean-code finding merged by the umbrella
  (or explicitly opted into by a user) is applicable through the shared engine.
  Consequence: their templates gain the apply fields (WS-1) and the workflow wording
  changes from "stop before apply" to "do not apply in their own run" (WS-3).
  The alternative — findings are never applicable — would instead require the
  umbrella to exclude them from Phase 4 and the consolidated template to drop its
  ddd/clean-code apply examples. Pick one; today both halves are asserted.
- **D2 — Where does the canonical finding schema live?** Recommended: a new
  `docs/report-contract.md` (single responsibility: the schema and nothing else),
  linked from every lens template and from the consolidator — not a further growth
  of `refactor-workflow.md`'s canonical section, which already owns Status/Apply-log
  vocabulary and should link the schema doc too.
- **D3 — Field naming.** Recommended: standardize on `Reader impact` and
  `Proposed change` (what the consolidator and shared implementer already parse);
  lens-flavoured fields (`Toward DDD`, `Problem now`, `Expected benefit`,
  `Impact`, `Fix`) become either renamed or explicitly-mapped aliases listed in the
  schema doc. No silent synonyms.

---

## WS-1 — Canonical finding schema; normalize the four non-conforming templates
*(fixes audit bug #2 — the consolidator cannot "carry verbatim" what four lenses never emit)*

Canonical per-finding fields (per D2/D3): `<a id>` anchor · ID `<lens>/<tier>-<n>` ·
Title · Lens/Principle line · **Location** · **Evidence** · **Reader impact** ·
**Proposed change** · **Risk** (Low|Medium|High) · **Related** · **Status**.
Canonical report sections: `## Summary`, findings by tier, `## Coverage`,
`## Apply log`, `## Outcome` (apply-capable reports), plus *available* (not
mandatory) `## Conflicts` and `## Grouped changes` skeletons so a standalone
reviewer has a sanctioned format for forks and groups (today those exist only in
the umbrella's template — solid/gof audits both flagged the dead path).

- [ ] **1.1** Write `docs/report-contract.md` (schema above + ID/anchor/filename
      rules + the alias table from D3). Link it from `refactor-workflow.md`'s
      canonical section and from all six lens templates + the consolidated template.
- [ ] **1.2 clean-architecture** `skills/clean-architecture/references/report-template.md`
      — add **Risk** (35-43; currently absent, breaking Phase-4 risk gating and the
      lens implementer's own "never apply High risk" rule), add `## Outcome`, rename
      `Impact`/`Fix` → canonical names (38-40; also `agents/analyzer.md:43-44`),
      move `## Apply log` *inside* the fenced skeleton and replace its table shape
      with the canonical timestamped line format (77-85 conflicts with
      `refactor-workflow.md:383-389` and `docs/refactor-agents/implementer.md:77-84`).
- [ ] **1.3 ddd** `skills/ddd/references/report-template.md` — add **Risk**,
      **Proposed change** (keep `Toward DDD` as the DDD-flavoured elaboration or
      alias per D3), **Reader impact** (41-51). Per D1, replace "no Status
      transition to `applied`" (15-16) with "this lens's own run never applies;
      findings remain applicable via the umbrella/shared engine".
- [ ] **1.4 clean-code** `skills/clean-code/references/report-template.md` — add
      **Risk**, **Status**, `## Apply log`, `## Outcome` (today: none of them, so
      `refactor-workflow.md:401-402`'s claim "Status: pending there just records…"
      is false for clean-code, and SKILL.md:84-87's promised opt-in apply has no
      fields to run on). Rename `<severity>` slot → `<tier>` (6; cosmetic but the
      umbrella says "tier").
- [ ] **1.5 gof** `skills/gof/references/report-template.md` — add **Evidence** and
      **Reader impact** (50-52 currently `Problem now`/`Expected benefit`; keep as
      aliases per D3), add `## Outcome`.
- [ ] **1.6 solid** `skills/solid/references/report-template.md` — add `## Outcome`
      (only gap); add the `<a id>` anchor lines to the Major/Minor skeleton stubs
      (53, 57 — only the Critical stub shows one).
- [ ] **1.7** All six templates: replace the in-fence
      `(../../../docs/status-vocabulary.md)` link — dead in every customer repo
      (solid :61, gof :74, ddd :68, test-quality :64, clean-arch equivalent) — with
      a non-link mention ("see the plugin's status vocabulary") or an inlined
      one-line legend.

Acceptance: WS-9's contract test passes over all six templates; consolidator can be
told "preserve ID, tier, Risk, Location, Evidence, Proposed change" truthfully.

## WS-2 — Apply-safety: lens-specific implementer dispatch
*(fixes audit bug #1 — umbrella silently skips test-quality's mutation & coverage gates — and bug #5)*

- [ ] **2.1** In `docs/refactor-workflow.md` Phase 4 and
      `skills/code-quality/SKILL.md` Phases 4–5: define the dispatch rule as an
      abstraction — *"dispatch the owning lens's `agents/implementer.md` when the
      lens ships one; otherwise the shared `docs/refactor-agents/implementer.md`"* —
      so a test-quality rec always runs through the implementer that wires the
      mutation gate and the coverage-non-regression gate, under the umbrella too.
      Keep model-tiering orthogonal (the gate instructions ride with the role file,
      not the model choice).
- [ ] **2.2** Amend `skills/test-quality/references/report-template.md:113-116`
      ("the shared implementer needs no special casing…") to match 2.1.
- [ ] **2.3** Fix gate invocation portability
      (`skills/test-quality/agents/{analyzer,reviewer,implementer}.md`): the bare
      relative `scripts/mutation_gate.py` + `--repo-root .` is only coherent when
      the audit target *is* this plugin repo. Resolve the plugin root explicitly
      (e.g. via the skill's own directory / `bin/mente-python` launcher convention)
      and pass the *target* as `--repo-root <target>` in all three role files.
- [ ] **2.4** State Gate B's behavior when Phase 0 recorded "coverage tool: none"
      (today only implicitly safe because the reviewer can't produce a deletion
      proof): make it explicit — no coverage tool ⇒ no deletion recs, recorded as
      a Coverage note. (`skills/test-quality/SKILL.md:87-92`,
      `agents/implementer.md:35-42`.)

Acceptance: an umbrella dry-run brief for a test-quality rec names the lens-local
implementer; the three invocation lines are cwd-independent.

## WS-3 — Analyze-only policy, stated once
*(fixes audit bug #3 — per D1)*

- [ ] **3.1** `docs/refactor-workflow.md:4-5, 401-402` — reword per D1: ddd and
      clean-code *runs* use Phases 0–3; their findings' applicability is a property
      of the report fields, not the lens.
- [ ] **3.2** `skills/code-quality/references/report-template.md` — Legend's
      "ddd (analyze-only)" (:37) gains the same clarification; keep (or, if D1
      resolves the other way, remove) the ddd/clean-code apply examples
      (:122, :124, :127, :151).
- [ ] **3.3** `skills/ddd/SKILL.md` guardrails (134-136, 166-167, 186-188) and
      `skills/clean-code/SKILL.md:84-87` — align wording with D1; clean-code's
      fix-routing paragraph also needs the deep-gear-report-required caveat (quick
      gear yields no rec IDs to apply — say so).

## WS-4 — ID-scheme sweep
*(fixes audit bug #4)*

- [ ] **4.1** `docs/refactor-agents/reviewer.md:70` — replace "(`C*/M*/N*`)" with
      "(`<lens>/<tier>-<n>` — see the lens's report template / docs/report-contract.md)".
- [ ] **4.2** `skills/ddd/agents/reviewer.md:30` — same fix (this one contradicts
      the template it cites *in the same sentence*).
- [ ] **4.3** Grep the tree for any remaining `C*/M*/N*` mentions.

## WS-5 — ddd realignment with the shared engine
*(worst-drifted lens; root cause: restates the pipeline instead of linking it)*

- [ ] **5.1** `skills/ddd/SKILL.md` analyze section — link
      `docs/refactor-workflow.md` like every other lens (it is the only lens that
      doesn't; "Mirrors `solid`'s pipeline" at :136 violates the workflow's own
      link-don't-restate rule at :13-15). Keep only ddd-specific deltas inline.
- [ ] **5.2** Phase 0 (138-142): add the structural-graph detection + verdict
      (its own `agents/analyzer.md:18-21` declares it as a required input that
      standalone runs never produce), the test-suite single run (fixes the
      "note whether the suite is green … this mode runs none" contradiction with
      report-template :30-31), stale-draft pre-clear, and post-report draft reap.
- [ ] **5.3** Phase 1/2 briefs (145-154): include `references/<language>.md` per
      the detect-and-load convention (java.md exists to prevent false findings and
      is currently unreachable standalone); point the reviewer at
      `docs/lens-overlap.md` (hub says "every lens's reviewer reads this"; ddd's
      only cross-refs SOLID and misses the clean-architecture carve at hub :52-61).
- [ ] **5.4** Report-dir exclusion: `.gitignore` edit (141-142) →
      `.git/info/exclude` per `refactor-workflow.md:98-101` (also: a "no code
      changes" mode shouldn't edit a committed file).
- [ ] **5.5** Phase vocabulary: renumber/rename ddd's analyze phases so "Phase 3"
      isn't a different gate than the shared Phase 3 (SKILL :166 "Phase 4 — Stop"
      vs workflow "Phases 0–3").
- [ ] **5.6** Small fixes: `/memory` → `/mente` (:130-131); drop "(repository
      issue #55)" from `references/python.md:117`; add pre-existing-`docs/domain/`
      handling (overwrite risk) to reviewer step 5 / SKILL 156-164.

## WS-6 — clean-code deep-gear completeness

- [ ] **6.1** `skills/clean-code/SKILL.md:64-70` — deep gear's Phase 0 must
      produce what its analyzer declares as inputs: structural-graph verdict,
      draft pre-clear, draft reap (today it invokes Phase 0 only for the report
      dir).
- [ ] **6.2** `agents/analyzer.md` — add a Proposed-change/Suggestion field to the
      draft entry format (the final template requires **Suggestion** but the draft
      never carries one, so the reviewer authors every suggestion from scratch).
- [ ] **6.3** Apply plumbing per D1 + WS-1.4 (fields) — then SKILL :84-87's routing
      to Phases 4–5 actually executes.

## WS-7 — Umbrella-specific gaps

- [ ] **7.1** `skills/code-quality/agents/consolidator.md` — say what to do with
      gof's graded A–F inventory + Maturity line (recommended: carry as an
      informational appendix / Coverage-notes subsection; never as findings).
      Today it silently vanishes.
- [ ] **7.2** `skills/code-quality/SKILL.md` Phase 2 — account for gof's
      unconditional HTML report (`GOF-REPORT-<date>.html`): either tell the gof
      reviewer to skip HTML in umbrella mode, or list it as a produced artifact.
      Recommended: skip in umbrella mode (one consolidated report is the product).
- [ ] **7.3** `skills/code-quality/SKILL.md` Phase 2/2.5 — add the draft-reap step
      (the umbrella replaces the shared Phase 2 where reaping lives; six drafts
      currently persist until the next run's pre-clear).
- [ ] **7.4** `references/report-template.md:109` — example `Lenses run:` line
      lists five lenses; add test-quality.
- [ ] **7.5** Consolidated template nit: "their standards' Severity rubrics"
      (:15-16) — test-quality's rubric section is titled "Tiers"; align one side.

## WS-8 — Stale-prose sweep (shared docs + lens bodies)

- [ ] **8.1** Two-lens-era singulars: `docs/refactor-agents/reviewer.md:58`
      ("the other lens"), `docs/refactor-workflow.md:146-148` ("the sibling
      lens") → "the overlapping lenses per the hub".
- [ ] **8.2** `docs/lens-overlap.md:12` and `docs/refactor-agents/reviewer.md:63`
      — "`*-reports/`" → `docs/reports/<lens>/`.
- [ ] **8.3** Interop framing wider than GoF↔SOLID: `skills/solid/SKILL.md:63-71`
      + `agents/reviewer.md:6-7` (add clean-arch DIP/boundary and test-quality
      over-mock handoffs); gof's is compliant.
- [ ] **8.4** Stale hard-coded language lists while `java.md` ships: solid
      SKILL :116-117; gof SKILL :5, 30-31, 89-90; clean-arch `agents/analyzer.md:17`,
      `agents/reviewer.md:12-13`, SKILL :124-125; ddd frontmatter :4-5 + file map
      :206-208. Replace with "list `references/` for the current set" per
      `refactor-workflow.md:127-128` (or name all three, consistently).
- [ ] **8.5** Java leave-behind (ArchUnit `DependencyRuleTest.java`) missing from
      every contract enumeration: clean-arch SKILL frontmatter :13-15 and :83-85,
      `agents/reviewer.md:16-17, 31-32`, `report-template.md:52-54`.
- [ ] **8.6** Dual role-doc reconciliation: `docs/refactor-workflow.md:29-31`
      (cast table points at `docs/refactor-agents/*`) vs lens SKILLs dispatching
      lens-local `agents/*`. State the rule once: lens-local role file wins when it
      exists; shared is the fallback — and align the draft entry-ID formats
      (`[D<n>]` shared vs `[A<n>]` clean-arch vs `[G<n>]` clean-code).
- [ ] **8.7** clean-arch `agents/reviewer.md:8-17` — add the structural-graph
      verdict to Inputs (analyzer has it; reviewer doesn't; shared reviewer does).
- [ ] **8.8** clean-code `references/report-template.md:7` — "other four lenses"
      → five.
- [ ] **8.9** gof rubric language stance: `references/patterns.md:1-7, 432-439` is
      Python-specific while the workflow demands language-agnostic rubrics
      (:111-113) — either generalize the rubric or state the precedence rule
      ("`references/<language>.md` overrides the rubric's language-specific
      signals"; java.md already contradicts it, e.g. Singleton grading).
- [ ] **8.10** gof HTML nits: `html-report.md:66-68, 78-80` "Overlap" → "Related";
      :38-39 Grade D labeled orange but hex `#ef4444` (red — near-identical to F's
      `#dc2626`); :75-77 tier palette "distinct" claim unverifiable (give hexes;
      Minor-blue clashes with Grade-B blue); :8 "Recommendations" → "Findings";
      :81 note the status-pill vocabulary is a stated lossy mapping of the
      canonical Status values.
- [ ] **8.11** clean-arch `references/python.md:5` — drop the pre-typescript.md
      "Other languages: dependency-cruiser/madge" remnant.
- [ ] **8.12** solid SKILL nits: bare plugin-root paths at :49, :54 → proper
      relative links; Invocation/Guardrails restatement (36-42, 76-92) → link the
      workflow per its own rule (restated prose has already drifted).
- [ ] **8.13** Optional naming: if "chunk review" is the official term (tests,
      cycle-gate spec), use the word once in solid's and clean-code's SKILL bodies.
- [ ] **8.14** Repo hygiene: delete leftover `docs/reports/clean-code/findings-draft.md`
      and `docs/reports/ddd/findings-draft.md` (pre-#112 banned basename order).
- [ ] **8.15** test-quality small items: reviewer must-keep list
      (`agents/reviewer.md:33-35`) gains the `<a id>` anchors call-out; rubric
      gains the 11 canonical Kind slugs (today they exist only in the two
      templates the analyzer is never told to read).
- [ ] **8.16** clean-arch underspecified analysis recipes (document or descope):
      CCP "git co-change" evidence has no command recipe; SDP has no numeric
      threshold guidance; the interactive `--cohesion` "go deeper?" offer has no
      placement in the flow; non-py/ts/java targets have no leave-behind story
      (state that explicitly as a limit).

## WS-9 — Contract tests (make the fixed contracts mechanical)

The audit's bugs cluster exactly where no test looks. Add
`tests/test_lens_report_contract.py`:

- [ ] **9.1** Every lens template defines the ID scheme `<lens>/<tier>-<n>` with
      the exact prefixes `clean-arch|ddd|solid|gof|clean-code|test-quality` and no
      file (template or role doc) mentions `C*/M*/N*`.
- [ ] **9.2** Every lens template's finding skeleton carries the canonical field
      set (Location, Evidence, Reader impact, Proposed change, Risk, Status) or a
      declared alias from `docs/report-contract.md`.
- [ ] **9.3** Apply-capable templates carry `## Apply log` + `## Outcome` inside
      the fenced skeleton; anchors (`<a id="<lens>-<tier>-<n>">`) appear in every
      tier's stub, not just Critical.
- [ ] **9.4** The umbrella/lens analyze-only wording matches D1 (grep-level
      assertion on the decided phrasing).
- [ ] **9.5** Phase-4 dispatch rule names the lens-local-implementer-first
      resolution (guards WS-2.1 against regression).
- [ ] **9.6** No fenced report skeleton contains a relative link into the plugin
      repo (`../../../docs/…`) — guards WS-1.7.

---

## Suggested execution order

1. **Gate D1–D3 with the human** (they shape WS-1/2/3/6).
2. WS-1 (schema + templates) and WS-4 (ID sweep) — unblock everything downstream.
3. WS-2 (apply safety) — the only finding with a real damage path.
4. WS-3, WS-5, WS-6, WS-7 — policy + per-lens realignment.
5. WS-8 (sweep) in one commit-series; WS-9 last so the tests assert the final state.
6. Full suite green after each workstream; `graphify update .` at the end.

Severity recap from the audit: 5 real bugs (WS-2 ×2, WS-1's schema gap, WS-3's
contradiction, WS-4's stale scheme), ~15 inconsistencies, ~20 nits — all enumerated
above; nothing from the six lens audits or the umbrella audit was dropped.
