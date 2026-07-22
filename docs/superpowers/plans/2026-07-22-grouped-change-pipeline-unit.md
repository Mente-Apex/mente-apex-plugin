# Grouped Change as a First-Class Pipeline Unit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carry a consolidator "Grouped change" (Primary + subsumed + separable riders) through the shared gate and apply phases so `/code-quality` (and any apply-capable lens) approves a group by title at Phase 3 and applies it as one TDD job at Phase 4, instead of re-deriving batches from a file-overlap heuristic.

**Architecture:** This is a **documentation / shared-contract change**, not runtime code. The refactor gate and apply are executed by *agents reading markdown* (`docs/refactor-workflow.md`, `docs/refactor-agents/implementer.md`) and the umbrella's consolidator writes the report the agents parse. So each task edits prose and is guarded by a **markdown-structure test** in the established `tests/test_*_skill_structure.py` style (read a file, assert it carries the required markers) — there is no behavior test because no Python executes the apply. Report-side first (group ID + subsumed/separable split), because the gate and apply reference it; then the shared gate, the shared apply, and finally the umbrella SKILL.md prose that restates the gate/apply mechanics.

**Tech Stack:** Markdown (skill/agent instructions); pytest 9.x on Python 3.14 in `.venv`; the structure-test idiom from `tests/test_clean_architecture_skill_structure.py`.

## Global Constraints

- **Test command:** `.venv/bin/python -m pytest -q` — **191 passed** at baseline; must stay green after every task.
- **New structure tests are dependency-free** (no PyYAML): `pathlib` + `re` only, mirroring `tests/test_clean_architecture_skill_structure.py`.
- **Behavior-preserving for ungrouped work.** A report with **no** `## Grouped changes` section must drive the apply phase identically to today (per-rec jobs, file-overlap ordering). This backward-compat fallback is the primary regression to guard, in prose and in a test assertion.
- **No new Status vocabulary.** A resolved rider reads `applied (via <primary-id>)`; do not introduce a new status word (spec §3.2, §9).
- **Reuse, don't fork** (the umbrella's own guardrail, `skills/code-quality/SKILL.md:131-134`): prefer thinning restated mechanics to a pointer over duplicating the group rules.
- **Scope:** touch only the five files in the table below. Do **not** teach single-lens (`solid`/`gof`/`clean-architecture`) report templates to emit groups — they hit the ungrouped fallback (spec §3.5). Do **not** touch `ddd`/`clean-code` apply paths — analyze-only.
- **Spec:** `docs/superpowers/specs/2026-07-22-grouped-change-pipeline-unit-design.md` is the source of truth; section references below (§N) point into it.

### Files touched

| File | Task | Change |
|---|---|---|
| `skills/code-quality/references/report-template.md` | 1 | Group ID in the `### One edit` banner; split apply-instruction; per-role rider annotation |
| `skills/code-quality/agents/consolidator.md` | 1 | Emit the stable group ID + the subsumed/separable apply-instruction split |
| `tests/test_code_quality_skill_structure.py` | 1–4 | New structure guard, extended each task |
| `docs/refactor-workflow.md` | 2, 3 | Phase 3 group-aware approval; Phase 4 "group = one job" + verification checkpoints + ungrouped fallback |
| `docs/refactor-agents/implementer.md` | 3 | Third apply unit "one group"; Status/Apply-log recording |
| `skills/code-quality/SKILL.md` | 4 | Reconcile the restated Phase 3/4 prose so it doesn't go stale |

---

## Task 1: Report-side — group ID + subsumed/separable split

The gate and apply read the group from the report, so the report must declare it unambiguously first. Add a stable `[group-<n>]` id to the `### One edit` banner and split its apply-instruction line into "subsumed resolve with the Primary" vs "separable is its own step." Author the same in the consolidator that writes the banner. Guard both with a new structure test.

**Files:**
- Create: `tests/test_code_quality_skill_structure.py`
- Modify: `skills/code-quality/references/report-template.md:87-94` (the `### One edit` banner + apply line)
- Modify: `skills/code-quality/agents/consolidator.md:55-65` (steps 5–6)

**Interfaces:**
- Produces: the report grammar `### [group-<n>] One edit — <title>` with each rider line annotated `*(subsumed …)*` or `*(separable …)*`, and a two-part apply-instruction. Tasks 2–4 rely on the markers `group-`, `subsumed`, `separable`, `Rides along` being present in these two files.

- [ ] **Step 1: Write the failing structure test**

Create `tests/test_code_quality_skill_structure.py`:

```python
"""Structural guard for the code-quality umbrella's group declaration.

Authored prose, not runtime code: assert the consolidated report format and the
consolidator role carry the group markers the shared gate+apply parse.
Dependency-free (no PyYAML), mirroring tests/test_clean_architecture_skill_structure.py.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CQ_DIR = REPO_ROOT / "skills" / "code-quality"


def read_cq(relative_path):
    """Read a file under skills/code-quality/, failing the test if absent."""
    target = CQ_DIR / relative_path
    assert target.is_file(), f"expected code-quality file missing: {target}"
    return target.read_text(encoding="utf-8")


def test_grouped_changes_banner_carries_group_id():
    text = read_cq("references/report-template.md")
    assert re.search(r"\[group-\d+\]", text), \
        "report-template.md Grouped changes banner must carry a [group-<n>] id"


def test_grouped_changes_apply_line_splits_rider_kinds():
    text = read_cq("references/report-template.md").lower()
    assert "subsumed" in text and "separable" in text, \
        "report-template.md must annotate riders subsumed vs separable"


def test_consolidator_emits_group_id_and_rider_split():
    text = read_cq("agents/consolidator.md")
    assert "group-" in text, "consolidator.md must instruct emitting a stable group-<n> id"
    lowered = text.lower()
    assert "subsumed" in lowered and "separable" in lowered, \
        "consolidator.md must instruct the subsumed/separable apply-instruction split"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_code_quality_skill_structure.py -v`
Expected: FAIL — the banner has no `[group-<n>]` id and neither file mentions `subsumed`/`separable` yet.

- [ ] **Step 3: Update the report template banner + apply line**

In `skills/code-quality/references/report-template.md`, replace the `### One edit` example block (currently lines 87-94, from `### One edit — <imperative title …` through `Apply \`clean-arch/major-1\`; the rest resolve with it.`) with:

```markdown
### [group-1] One edit — <imperative title of the physical change>   [resolves <k> findings across <j> lenses]

Give every group a stable id (`group-1`, `group-2`, …) so the gate and apply can
reference it. The group's tier is its **Primary's** tier.

- **Primary** · `clean-arch/major-1` — <what it is, one line>. *Owns the fix.*
- **Same change** · `clean-arch/major-2` — <the same edge, a different violation>. *(subsumed — resolves with the Primary; not vetoable)*
- **Fix mechanism** · `solid/major-5` — <the how, not a separate edit>. *(subsumed)*
- **Sub-symptom** · `clean-arch/minor-2` — <vanishes once the primary lands>. *(subsumed)*
- **Rides along** · `clean-code/minor-5` — <adjacent cleanup enabled by the primary>. *(separable — its own step in the same job; vetoable)*

Apply `clean-arch/major-1` (subsumed riders resolve with it); then apply each
**Rides along** rider as a follow-on step in the *same* job, unless vetoed at the gate.
Omit any rider role that has no member. A group whose riders are all subsumed keeps
just the first clause.
```

- [ ] **Step 4: Update the consolidator to author the id + split**

In `skills/code-quality/agents/consolidator.md`, replace step 5 (lines 55-59, the `Build the Grouped changes section.` paragraph) with:

```markdown
5. **Build the Grouped changes section.** Whenever an overlap resolves to **one
   physical edit** touching 2+ findings, add a `### [group-<n>] One edit — …` banner —
   give each group a stable id (`group-1`, `group-2`, …) so the shared gate and apply
   can address it. List the Primary and each related finding with its label and a
   one-line "what it is", and **annotate each rider for apply**: `Same change` /
   `Fix mechanism` / `Sub-symptom` are **subsumed** (they resolve automatically with
   the Primary's edit — mark them `*(subsumed)*`), while `Rides along` is **separable**
   (its own follow-on edit in the same job, vetoable — mark it `*(separable)*`). End the
   banner with the two-part apply-instruction: apply the Primary (subsumed riders resolve
   with it); then apply each separable rider as a follow-on step unless vetoed. The
   group's tier is the Primary's tier. A finding that stands alone never appears here.
   If nothing clustered, omit the section.
```

- [ ] **Step 5: Run the test to verify it passes, then the full suite**

Run: `.venv/bin/python -m pytest tests/test_code_quality_skill_structure.py -v`
Expected: PASS (3 tests).
Run: `.venv/bin/python -m pytest -q`
Expected: PASS — 194 passed (191 + 3 new).

- [ ] **Step 6: Commit**

```bash
git add tests/test_code_quality_skill_structure.py skills/code-quality/references/report-template.md skills/code-quality/agents/consolidator.md
git commit -m "feat(code-quality): declare groups with a stable id + subsumed/separable split"
```

---

## Task 2: Shared gate — Phase 3 group-aware approval

Teach the shared decision gate to present groups as units: approvable by title/tier (tier = Primary's), with the one sub-group choice being to veto a separable rider. A rider only lands through its Primary.

**Files:**
- Modify: `docs/refactor-workflow.md:85-91` (Phase 3 — decision gate)
- Modify: `tests/test_code_quality_skill_structure.py` (add a Phase-3 guard)

**Interfaces:**
- Consumes: the report grammar from Task 1 (`[group-<n>]`, subsumed/separable annotations).
- Produces: Phase 3 prose containing the approval-by-group path and the separable-veto rule; later tasks don't depend on it.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_code_quality_skill_structure.py`:

```python
def test_workflow_phase3_is_group_aware():
    text = (REPO_ROOT / "docs" / "refactor-workflow.md").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "grouped change" in lowered or "group" in lowered, \
        "Phase 3 must let the human approve a group"
    assert "veto" in lowered and "separable" in lowered, \
        "Phase 3 must describe vetoing a separable rider"
    assert "primary's tier" in lowered or "tier of its primary" in lowered, \
        "Phase 3 must state a group is approved at its Primary's tier"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_code_quality_skill_structure.py::test_workflow_phase3_is_group_aware -v`
Expected: FAIL — Phase 3 says only "by tier … or by ID".

- [ ] **Step 3: Rewrite Phase 3**

In `docs/refactor-workflow.md`, replace the Phase 3 body (lines 87-91, the paragraph beginning "Read the final report…") with:

```markdown
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
```

- [ ] **Step 4: Run the test + full suite**

Run: `.venv/bin/python -m pytest tests/test_code_quality_skill_structure.py::test_workflow_phase3_is_group_aware -v`
Expected: PASS.
Run: `.venv/bin/python -m pytest -q`
Expected: PASS — 195 passed.

- [ ] **Step 5: Commit**

```bash
git add docs/refactor-workflow.md tests/test_code_quality_skill_structure.py
git commit -m "feat(refactor-workflow): Phase 3 approves grouped changes as units"
```

---

## Task 3: Shared apply — Phase 4 "group = one job" + implementer role

Replace the file-overlap batching with "a declared group is one job" (keeping file-overlap as the ungrouped fallback), define the Primary-then-separable verification checkpoints, and give the implementer role the third apply unit plus the Status/Apply-log recording.

**Files:**
- Modify: `docs/refactor-workflow.md:135-142` (Phase 4 — batching/ordering) and `:106-113` (Phase 4 intro, add the group-job rule)
- Modify: `docs/refactor-agents/implementer.md` (add the group unit + recording)
- Modify: `tests/test_code_quality_skill_structure.py` (add Phase-4 + implementer guards)

**Interfaces:**
- Consumes: the report grammar (Task 1) and the group-aware gate (Task 2).
- Produces: Phase 4 + implementer prose defining one-job-per-group, the checkpoint order, and the four Status outcomes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_code_quality_skill_structure.py`:

```python
def test_workflow_phase4_group_is_one_job():
    text = (REPO_ROOT / "docs" / "refactor-workflow.md").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "one job" in lowered and "group" in lowered, \
        "Phase 4 must map a declared group to one job"
    assert "ungrouped" in lowered, \
        "Phase 4 must retain the ungrouped (file-overlap) fallback"
    assert "separable" in lowered and "revert" in lowered, \
        "Phase 4 must describe reverting a failed separable rider alone"


def test_implementer_has_group_apply_unit():
    text = (REPO_ROOT / "docs" / "refactor-agents" / "implementer.md").read_text(encoding="utf-8")
    assert "group" in text.lower(), "implementer must gain a group apply unit"
    assert "applied (via" in text, \
        "implementer must record subsumed riders as 'applied (via <primary>)'"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_code_quality_skill_structure.py -k "phase4 or implementer" -v`
Expected: FAIL (2 tests) — no "one job" grouping, no `applied (via`.

- [ ] **Step 3: Rewrite Phase 4 batching + ordering**

In `docs/refactor-workflow.md`, replace the batching paragraph (lines 135-142, beginning "Order the queue first: recs touching the same file form one **chain**…") with:

```markdown
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
```

- [ ] **Step 4: Add the group-job rule to the Phase 4 dispatch sentence**

In `docs/refactor-workflow.md`, in the paragraph at lines 123-133 (beginning "**Each approved rec is applied by dispatching a TDD refactor job**"), change the phrase "dispatches **one job per rec** (or per dependent chain)" to:

```markdown
dispatches **one job per group** (a declared `## Grouped changes` entry), **or one job
per rec** / dependent chain for ungrouped recs,
```

- [ ] **Step 5: Rewrite the implementer role**

In `docs/refactor-agents/implementer.md`, replace the "## Per-recommendation loop" section (lines 25-37) with:

```markdown
## Per-unit loop (one rec, one chain, or one group)

You apply exactly one unit: a standalone rec, a dependent chain, or a **grouped
change** (a `## Grouped changes` entry — a Primary plus subsumed and separable riders).

1. Read the unit and every file it cites. For a group, read the banner: the **Primary**,
   its **subsumed** riders (`Same change` / `Fix mechanism` / `Sub-symptom` — resolved by
   the Primary's edit), and its **separable** (`Rides along`) riders (approved ones are
   their own follow-on step; vetoed ones are skipped).
2. Build the refactor-job input (see
   [skills/tdd/references/refactor-jobs.md](../../skills/tdd/references/refactor-jobs.md)):
   `targets` = the cited files; `change` = the Primary's Proposed change verbatim, plus
   each approved separable rider's change as an explicit follow-on step; `test_command`
   + `baseline_status` = as given; `coverage` = per the gate; `new_behavior` = any part
   the rec marks as new behavior (usually none).
3. Dispatch the TDD refactor job. For a group, it verifies after the Primary+subsumed
   edit, then after each separable rider — a failed separable rider reverts alone.
4. Record outcomes into each finding's Status line and append Apply-log lines, using the
   report's exact fields:
   - **Primary** → `applied` or `failed (reverted)`.
   - **Subsumed rider** → `applied (via <primary-id>)`; Apply-log:
     `<ts> [<rider>] applied — subsumed by <primary> (no separate edit)`.
   - **Approved separable rider** → `applied` (its own edit) or `failed (reverted)`.
   - **Vetoed separable rider** → `skipped (not approved)`.
5. In a chain, a mid-chain revert invalidates dependents — mark them `skipped` with a
   note pointing at the failed rec. A group's Primary revert fails the group; a separable
   revert leaves the Primary and other riders intact.
```

- [ ] **Step 6: Run the tests + full suite**

Run: `.venv/bin/python -m pytest tests/test_code_quality_skill_structure.py -v`
Expected: PASS (7 tests total in this file).
Run: `.venv/bin/python -m pytest -q`
Expected: PASS — 197 passed.

- [ ] **Step 7: Commit**

```bash
git add docs/refactor-workflow.md docs/refactor-agents/implementer.md tests/test_code_quality_skill_structure.py
git commit -m "feat(refactor-workflow): apply a grouped change as one TDD job with per-rider checkpoints"
```

---

## Task 4: Umbrella SKILL.md — reconcile the restated Phase 3/4 prose

`skills/code-quality/SKILL.md` restates the gate/apply mechanics ("by tier or ID"; "one queue … suite green after each"). Now that the shared contract is group-aware, those restatements are stale. Thin them to a pointer at the shared doc (per the skill's own "Reuse, don't fork" guardrail) with a one-line mention that groups are approved/applied as units.

**Files:**
- Modify: `skills/code-quality/SKILL.md:104-121` (Phase 3 and Phases 4–5 paragraphs)
- Modify: `tests/test_code_quality_skill_structure.py` (add a guard)

**Interfaces:**
- Consumes: the group-aware shared Phase 3/4 from Tasks 2–3.
- Produces: nothing downstream depends on it.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_code_quality_skill_structure.py`:

```python
def test_umbrella_skill_prose_is_group_aware():
    text = read_cq("SKILL.md")
    lowered = text.lower()
    assert "group" in lowered, \
        "umbrella SKILL.md must mention grouped-change approval/apply"
    # the stale 'by tier or ID' phrasing must no longer be the only stated path
    assert "grouped change" in lowered or "as units" in lowered, \
        "umbrella SKILL.md must state groups are approved/applied as units"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_code_quality_skill_structure.py::test_umbrella_skill_prose_is_group_aware -v`
Expected: FAIL — SKILL.md says only "by tier or ID".

- [ ] **Step 3: Thin the Phase 3 paragraph**

In `skills/code-quality/SKILL.md`, replace the Phase 3 paragraph (lines 104-112, "### Phase 3 — Decision gate…") with:

```markdown
### Phase 3 — Decision gate (human, shared)

Follow the shared workflow's Phase 3 on the **consolidated** report: present counts by
tier, the top wins across all lenses, anything High-risk, and any *Unresolved tensions*
the consolidator surfaced (e.g. Singleton ↔ DIP). The consolidated report carries a
`## Grouped changes` section, so the shared gate presents those as units — approvable by
title/id or by their Primary's tier, with separable `Rides along` riders individually
vetoable. Standalone recs keep their verbatim IDs, Risk, and Status; approve by tier or
id as usual. **"None — just the report" is a first-class outcome**; stop there gracefully.
```

- [ ] **Step 4: Thin the Phases 4–5 paragraph**

In `skills/code-quality/SKILL.md`, replace the Phases 4–5 paragraph (lines 114-121, "### Phases 4–5 — Apply via TDD…") with:

```markdown
### Phases 4–5 — Apply via TDD & final review (shared, opt-in)

Approved recs apply through the shared Phase 4/5 (the TDD refactor engine), **unchanged
by this skill**: a declared grouped change is one job (Primary + subsumed riders, then
each approved separable rider, verified per the shared workflow), and ungrouped recs
apply per-rec. Each merged finding keeps its lens origin, so the implementer applies it
with the fix idiom that lens intended. One working branch (`code-quality/<slug>`), jobs
ordered Critical → Major → Minor, suite green after each. Then verify the suite yourself
and offer to commit/PR via `/ship`; never auto-publish.
```

- [ ] **Step 5: Run the test + full suite**

Run: `.venv/bin/python -m pytest tests/test_code_quality_skill_structure.py::test_umbrella_skill_prose_is_group_aware -v`
Expected: PASS.
Run: `.venv/bin/python -m pytest -q`
Expected: PASS — 198 passed.

- [ ] **Step 6: Commit**

```bash
git add skills/code-quality/SKILL.md tests/test_code_quality_skill_structure.py
git commit -m "docs(code-quality): reconcile umbrella Phase 3/4 prose with group-aware shared contract"
```

---

## Definition of done

- `.venv/bin/python -m pytest -q` → **198 passed** (191 baseline + 7 new structure assertions).
- `docs/refactor-workflow.md` Phase 3 approves groups by title/tier; Phase 4 maps a group to one job with Primary-then-separable checkpoints and keeps the ungrouped file-overlap fallback.
- `docs/refactor-agents/implementer.md` has the third apply unit and the four Status outcomes incl. `applied (via <primary>)`.
- `skills/code-quality/{references/report-template.md,agents/consolidator.md}` declare a `[group-<n>]` id and the subsumed/separable split.
- `skills/code-quality/SKILL.md` no longer restates a stale "by tier or ID"-only gate.
- Backward compatibility: a report with no `## Grouped changes` section is unaffected — asserted by the retained-fallback wording (Task 3) and drives the per-rec path.
- Offer to `/ship` the branch `code-quality/grouped-change-unit`; never auto-publish.
```