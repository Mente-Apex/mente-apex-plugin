# Clean-Code Substrate + Reports Convention — Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `clean-code` from a standalone review skill into a hardened, shared craftsmanship **substrate** — one canonical `docs/clean-code-standard.md` consumed by the shared implementer role and `tdd` (so all produced/refactored code is clean by construction) plus a thin two-gear `/clean-code` review — and consolidate every lens's reports under `docs/reports/<lens>/`.

**Architecture:** Skills are authored Markdown, not runtime code; correctness is enforced by a dependency-free structural pytest guard (`tests/test_clean_code_skill_structure.py`) plus trigger/behaviour evals (`evals/clean-code-evals.json`), mirroring the `ddd`/`solid`/`gof` house pattern. The 15 leverage-ranked principles already living in `skills/clean-code/SKILL.md` are **moved verbatim** into the canonical standard, which then gains three missing chapters (Boundaries/learning tests, Kent Beck's 4 rules of Simple Design, the Smells & Heuristics checklist), a severity rubric, and a review-mode section. The thin skill and the shared consumers **link** that one standard; nothing copies it.

**Tech Stack:** Markdown skill/doc files; Python 3.14 stdlib only for the structural test (`pathlib`, `re`, `json` — **no PyYAML**); `pytest` (repo runner). This plan is Plan 1 of 2; Plan 2 (`clean-architecture` lens + overlap-hub migration + manifest registration) builds on this foundation.

## Global Constraints

- **Source spec:** `docs/superpowers/specs/2026-07-20-clean-code-and-clean-architecture-integration-design.md` — every task traces to it.
- **Test runner (pinned):** `.venv/bin/python -m pytest` — the repo targets **Python 3.14** (`.python-version` = 3.14.6). Bare `python3` may resolve to a system 3.9 that lacks `tomllib`, which makes `tests/test_skill_integrity.py` fail to *collect*. In a fresh worktree without `.venv`: `python3.14 -m venv .venv && .venv/bin/python -m pip install pytest` first.
- **Baseline is red by exactly one pre-existing failure:** `test_skill_integrity.py::test_version_mirrors_match` — `pyproject.toml` = `0.11.0` while both manifests = `0.12.0`. Task 1 aligns it. After Task 1 the suite is fully green; every later task ends green.
- **Three version mirrors** must stay equal: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and `pyproject.toml`. This plan sets all to `0.12.0` and does **not** bump the plugin version (the feature ships at the end of Plan 2, which bumps to `0.13.0`).
- **House skill layout (verbatim):** `skills/<name>/SKILL.md`, `skills/<name>/references/*.md`, `skills/<name>/agents/*.md`.
- **SKILL.md frontmatter fields (verbatim):** `name:`, `description:` (block scalar), `user-invocable: true`, `metadata:` → `version:`. Rebuilt `clean-code` version is `"0.2.0"`.
- **Single source of truth:** the canonical standard lives at `docs/clean-code-standard.md`. The thin skill, the shared implementer role, and `tdd` **link** it; no principle text is duplicated.
- **Link-resolution guard:** `test_skill_integrity.py::test_relative_markdown_links_resolve` scans `skills/{gof,solid,tdd}/**`, `docs/refactor-workflow.md`, `docs/refactor-agents/*.md`, `docs/solid-gof-overlap.md`, `docs/git-convention.md`. Any relative markdown link added to those files must resolve — so create `docs/clean-code-standard.md` (Task 2) **before** linking to it (Tasks 6–7).
- **No PyYAML.** Structural tests parse frontmatter with `re`/string ops (mirroring `tests/test_ddd_skill_structure.py`).
- **Reports convention (new):** every lens writes to `docs/reports/<lens>/` (git-excluded), replacing `solid-reports/` / `gof-reports/` / `ddd-reports/`.
- **Descriptive names only** — no single-letter/abbreviated variables, including in comprehensions (applies to the test module).
- **Git convention:** all work on the existing `clean-architecture/skills` branch (off `main`); offer (never auto) commit + PR at the end (`docs/git-convention.md`).

---

## File Structure

Files created/modified, each with one responsibility:

- `pyproject.toml` — align the third version mirror to `0.12.0` (fix pre-existing drift).
- `docs/clean-code-standard.md` — **NEW** canonical standard: the 15 ported principles + 3 new chapters + severity rubric + review-mode + meta-rule. Single source of truth.
- `skills/clean-code/SKILL.md` — **rewritten thin**: write-time default + two-gear review (quick inline / deep verified), points at the standard, defers structural findings up-ladder.
- `skills/clean-code/agents/analyzer.md` — deep-gear read-only analyzer role.
- `skills/clean-code/agents/reviewer.md` — deep-gear verifier + report author.
- `skills/clean-code/references/report-template.md` — deep-gear review report format.
- `docs/refactor-agents/implementer.md` — **modified**: applied code follows the standard (link).
- `skills/tdd/references/refactor-jobs.md` — **modified**: the refactor step cleans to the standard (link).
- `docs/refactor-workflow.md` — **modified**: Phase 0 report dir → `docs/reports/<lens>/`.
- `skills/solid/**`, `skills/gof/**`, `skills/ddd/**` — **modified**: report-path references → `docs/reports/<lens>/`.
- `.gitignore` — **modified**: exclude `docs/reports/` (replacing the `solid-reports/` entry).
- `tests/test_clean_code_skill_structure.py` — **NEW** dependency-free structural guard.
- `evals/clean-code-evals.json` — **NEW** trigger + behaviour evals.

**Task boundaries:** one file (or tightly-coupled pair) per task; each task appends its own assertions to the shared structural test and ends green + committed.

---

## Task 0: Working branch

- [ ] **Step 1: Ensure the working branch**

Run:
```bash
cd /Users/ai/Projects/mente-apex-plugin
git checkout clean-architecture/skills 2>/dev/null || git checkout -b clean-architecture/skills
git status
```
Expected: on branch `clean-architecture/skills` (already holds the spec commit), clean tree.

---

## Task 1: Green the baseline — align the version mirror

**Files:**
- Modify: `pyproject.toml:3`

**Interfaces:**
- Produces: a fully-green baseline (`test_version_mirrors_match` passes) so every later task's "suite green" is meaningful.

- [ ] **Step 1: Confirm the pre-existing failure**

Run: `.venv/bin/python -m pytest tests/test_skill_integrity.py::test_version_mirrors_match -q`
Expected: FAIL — `pyproject=0.11.0 ... plugin.json=0.12.0`.

- [ ] **Step 2: Align pyproject to the manifests**

In `pyproject.toml`, change line 3 from:
```toml
version = "0.11.0"  # mirrors .claude-plugin/plugin.json (canonical source of truth)
```
to:
```toml
version = "0.12.0"  # mirrors .claude-plugin/plugin.json (canonical source of truth)
```
Change nothing else.

- [ ] **Step 3: Verify the mirror test passes**

Run: `.venv/bin/python -m pytest tests/test_skill_integrity.py::test_version_mirrors_match -q`
Expected: PASS.

- [ ] **Step 4: Verify the whole baseline is now green**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (112 passed).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "fix: align pyproject version mirror to 0.12.0 (pre-existing drift)"
```

---

## Task 2: Structural test harness + `docs/clean-code-standard.md`

**Files:**
- Create: `tests/test_clean_code_skill_structure.py`
- Create: `docs/clean-code-standard.md`

**Interfaces:**
- Produces: the helpers `REPO_ROOT`, `read_repo_file(relative_path)`, `read_skill_file(relative_path)`, `parse_frontmatter(text)` reused by every later task. `parse_frontmatter` returns `dict[str, str]` of top-level `key: value` pairs plus `"_body"`. No PyYAML.
- Produces: `docs/clean-code-standard.md` — the canonical standard every consumer links.

- [ ] **Step 1: Write the failing structural test**

Create `tests/test_clean_code_skill_structure.py`:
```python
"""Structural guard for the clean-code substrate.

clean-code is authored prose (a shared standard + a thin review skill), not
runtime code, so its "tests" assert each file exists and carries the
sections/links the ecosystem depends on. Dependency-free on purpose: PyYAML is
not installed, so frontmatter is parsed with string ops only (same discipline as
test_ddd_skill_structure.py).
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLEAN_CODE_SKILL_DIR = REPO_ROOT / "skills" / "clean-code"
CLEAN_CODE_STANDARD = REPO_ROOT / "docs" / "clean-code-standard.md"


def read_repo_file(relative_path):
    """Read a repo-relative file, failing the test if it is absent."""
    target = REPO_ROOT / relative_path
    assert target.is_file(), f"expected file missing: {target}"
    return target.read_text(encoding="utf-8")


def read_skill_file(relative_path):
    """Read a file under skills/clean-code/, failing the test if absent."""
    target = CLEAN_CODE_SKILL_DIR / relative_path
    assert target.is_file(), f"expected skill file missing: {target}"
    return target.read_text(encoding="utf-8")


def parse_frontmatter(text):
    """Parse leading --- frontmatter into {key: value, '_body': rest}. No PyYAML."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert match, "file does not start with a --- frontmatter block"
    raw_frontmatter, body = match.group(1), match.group(2)
    fields = {"_body": body}
    for line in raw_frontmatter.splitlines():
        key_value = re.match(r"^([A-Za-z0-9_-]+):\s?(.*)$", line)
        if key_value:
            fields[key_value.group(1)] = key_value.group(2)
    return fields


def test_standard_has_the_fifteen_principles_and_three_new_chapters():
    text = CLEAN_CODE_STANDARD.read_text(encoding="utf-8")
    lowered = text.lower()
    # the 15 ported leverage-ranked principle anchors
    ported_anchors = [
        "meaningful names",
        "single responsibility",
        "functions do one thing",
        "don't repeat yourself",
        "high cohesion",
        "command-query separation",
        "one level of abstraction",
        "flag argument",
        "never return null",
        "comments are a last resort",
        "law of demeter",
        "encapsulate conditionals",
        "clean tests",
        "consistent formatting",
        "boy scout rule",
    ]
    missing_ported = [anchor for anchor in ported_anchors if anchor not in lowered]
    assert not missing_ported, f"standard missing ported principles: {missing_ported}"
    # the three NEW chapters
    for new_chapter in ["Boundaries", "Simple Design", "Smells & Heuristics"]:
        assert new_chapter in text, f"standard missing new chapter: {new_chapter}"
    for new_marker in ["learning test", "runs all tests", "expresses intent"]:
        assert new_marker in lowered, f"standard missing new content: {new_marker}"
    # the meta-rule + severity rubric survive the move
    assert "meta-rule" in lowered
    for severity in ["High", "Medium", "Low"]:
        assert severity in text, f"standard missing severity level: {severity}"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py -q`
Expected: FAIL — `expected file missing: .../docs/clean-code-standard.md`.

- [ ] **Step 3: Author `docs/clean-code-standard.md`**

Create the file with this exact head, then **port principles 1–15, the meta-rule, and the Review-mode + Severity blocks verbatim from the current `skills/clean-code/SKILL.md` (its lines 47–252)** — that content is already the hardened text; do not rewrite it, only move it under the structure below. Then add the three new chapters exactly as written here.

````markdown
# Clean-code standard

The single source of truth for line-level craft in this repo, distilled from
Robert C. Martin's *Clean Code* and deliberately de-dogmatized. The one idea
under every rule: **code is written once and read many times — optimize for the
next person who has to understand and change it.**

This file is a **substrate**, not just a review checklist. It is linked (never
copied) by the shared implementer role and by `tdd`, so every refactor and every
test-first line comes out clean by construction; and by `skills/clean-code/` for
standalone review. Harden the craft here, once.

The rules are **ranked by leverage** — spend attention top-down. Each carries a
**"Where this bends"** note: misapplying a clean-code rule is itself a clean-code
problem.

---

## The principles, by leverage

<!-- PORT VERBATIM from skills/clean-code/SKILL.md lines 47–183:
     the fifteen "### N." principles (Meaningful names … Boy Scout Rule),
     each with its "Where this bends" note, and the "## The meta-rule" section.
     Do not reword; this is a move, not a rewrite. -->

---

## Boundaries — keep third-party code at arm's length

External code should not shape yours. When you depend on a library, an SDK, an
HTTP client, or an ORM, wrap it behind an interface **you** own and convert at the
edge — don't let a vendor type spread through your domain, where every future
swap or breaking change then touches everything.

**Learning tests.** When adopting or upgrading an unfamiliar third-party API,
write small tests that exercise it *the way you intend to use it*. They teach you
the API against the real thing (not the docs), and they become an upgrade
tripwire: when the vendor changes behaviour, your learning tests fail first,
cheaply, instead of your product failing in production.

**Where this bends:** don't wrap a stable stdlib type (`list`, `dict`,
`pathlib.Path`) you will never replace — that is ceremony. Wrap the *volatile,
replaceable, or awkward* externals. The concern is coupling your core to a
foreign model, not banning direct use of the platform.

## Simple Design — Kent Beck's four rules

A design-quality heuristic, applied **in priority order**:

1. **Runs all tests** — it must actually work; a testable design is almost always
   a better-factored one.
2. **Expresses intent** — expressive names, small units, no surprises; the reader
   can see *why*.
3. **No duplication** — one source of truth (respecting the false-DRY caution in
   principle #4).
4. **Fewest elements** — no needless classes, methods, or indirection (YAGNI).

Use it as the review's ordering lens: correctness first, then clarity, then
duplication, then minimalism.

**Where this bends:** rules 2–4 can pull against each other — deleting a
well-named helper purely to cut element count can hurt intent. When they
conflict, **intent/readability wins**; the ordering is a tie-breaker, not a
bludgeon.

## Smells & Heuristics — the checklist

A memory aid drawn from *Clean Code* ch 17, not a rulebook. Scan for these; when
one bites, fix it by the numbered principle above and file it at the severity its
reader-cost warrants.

- **Comments:** obsolete, redundant, or commented-out code (→ #10).
- **Functions:** too many arguments, flag arguments, dead functions (→ #3, #8).
- **General:** duplication; code at the wrong level of abstraction; dead code;
  vertical separation of related code; inconsistency; feature envy; magic
  numbers; misplaced responsibility; obscured intent; negative conditionals
  (→ #2, #4, #7, #12).
- **Names:** don't describe intent; ambiguous; encoded; wrong scope (→ #1).
- **Tests:** insufficient, coverage gaps, skipped, or slow (→ #13).

**Where this bends:** the catalogue is a prompt, not a quota. A matched smell name
is not a finding — it must actually cost the reader (see *Severity*). Don't
manufacture findings to look thorough.

---

## Review mode

<!-- PORT VERBATIM from skills/clean-code/SKILL.md lines 187–238:
     the "## Review mode" steps, the "### Severity" (High/Medium/Low), and the
     "### Suggested output" block. Do not reword. -->

---

## Scope — what this standard does not do

<!-- PORT VERBATIM from skills/clean-code/SKILL.md lines 242–252 (the "## Scope"
     bullets: no unprompted mass-rewrite; not a linter/formatter config; not a
     replacement for security-review or /ship). -->
````

When porting, delete each `<!-- PORT … -->` comment and paste the referenced
lines in its place. Keep every "Where this bends" note intact.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_clean_code_skill_structure.py docs/clean-code-standard.md
git commit -m "feat(clean-code): canonical standard doc (15 principles + boundaries, simple design, smells)"
```

---

## Task 3: Thin `skills/clean-code/SKILL.md`

**Files:**
- Modify (full rewrite): `skills/clean-code/SKILL.md`
- Modify: `tests/test_clean_code_skill_structure.py`

**Interfaces:**
- Consumes: `read_skill_file`, `parse_frontmatter` from Task 2.
- Produces: the thin skill that links the standard and runs the two-gear review.

- [ ] **Step 1: Append the failing test**

Add to `tests/test_clean_code_skill_structure.py`:
```python
def test_skill_md_is_thin_and_links_the_standard():
    fields = parse_frontmatter(read_skill_file("SKILL.md"))
    assert fields.get("name") == "clean-code"
    assert fields.get("user-invocable") == "true"
    frontmatter_text = read_skill_file("SKILL.md").split("---")[1]
    assert re.search(r'version:\s*"0\.2\.0"', frontmatter_text), "metadata.version must be 0.2.0"
    body = fields["_body"]
    lowered = body.lower()
    # links the single source of truth rather than restating it
    assert "docs/clean-code-standard.md" in body, "SKILL.md must link the canonical standard"
    # the two gears
    assert "quick" in lowered and "deep" in lowered, "SKILL.md must describe the two review gears"
    # defers structural findings up-ladder (non-overlap contract)
    for sibling in ["solid", "gof"]:
        assert sibling in lowered, f"SKILL.md must defer up-ladder to {sibling}"
    # the substrate framing
    assert "substrate" in lowered or "written by construction" in lowered or "by construction" in lowered
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py::test_skill_md_is_thin_and_links_the_standard -q`
Expected: FAIL — old SKILL.md has version 0.1.0 and no link to the standard.

- [ ] **Step 3: Rewrite `skills/clean-code/SKILL.md`**

Replace the entire file with:
````markdown
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
  version: "0.2.0"
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
  cleanliness with no other lens in play.

## Review — two gears

Scale effort to scope. **Read the standard first**, then:

- **Quick (default for a diff or a few files).** One read-through against the
  standard; report findings inline (the *Suggested output* format in the
  standard). No subagents, no report file — the common case stays light.
- **Deep (a PR, a module, or on request).** The two-stage verified pipeline:
  dispatch `agents/analyzer.md` (read-only draft) then `agents/reviewer.md`
  (re-verifies every finding against the code, prunes false positives), writing a
  report to `docs/reports/clean-code/CLEAN-CODE-REPORT-<YYYY-MM-DD>.md` per
  `references/report-template.md`. Create `docs/reports/clean-code/` git-excluded,
  as in `../../docs/refactor-workflow.md` Phase 0.

## Non-overlap — defer up-ladder

clean-code owns line-level craft only. When a finding is really a **structural**
problem, name it and hand it up the altitude ladder rather than solving it here:

- responsibilities / dependency direction / the five principles → **`/solid`**
- a recurring object-collaboration that wants a pattern → **`/gof`**
- domain modelling (aggregates, ubiquitous language, ports) → **`/ddd`**
- the component/dependency graph, cycles, framework-as-detail → **`/clean-architecture`**

## Apply — opt-in only

Review stops at findings. Code-level nits are cheap to fix by hand and riskiest to
mass-apply, so apply only when the user asks — then reuse the shared
implementer/TDD path (`../../docs/refactor-workflow.md` Phases 4–5), which already
cleans to this same standard.

## Guardrails

- **The standard is the single source of truth** — this skill and every consumer
  link `docs/clean-code-standard.md`; never restate or fork it.
- **Judgment, not dogma.** Honour every "Where this bends" note; a clean review is
  a few high-signal items, not a pile of style nits. If nothing meaningful is
  wrong, say so.
- **Read-only by default.** Surface and explain; don't rewrite unless asked.
````

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py::test_skill_md_is_thin_and_links_the_standard -q`
Expected: PASS.

- [ ] **Step 5: Confirm repo-wide skill guards still pass**

Run: `.venv/bin/python -m pytest tests/test_skill_integrity.py tests/test_skill_shell_safety.py -q`
Expected: PASS (frontmatter valid; no `echo "$VAR" | python3`).

- [ ] **Step 6: Commit**

```bash
git add skills/clean-code/SKILL.md tests/test_clean_code_skill_structure.py
git commit -m "feat(clean-code): thin two-gear skill linking the canonical standard"
```

---

## Task 4: Deep-gear agents — `analyzer.md` + `reviewer.md`

**Files:**
- Create: `skills/clean-code/agents/analyzer.md`
- Create: `skills/clean-code/agents/reviewer.md`
- Modify: `tests/test_clean_code_skill_structure.py`

**Interfaces:**
- Consumes: `read_skill_file`; the analyzer writes `docs/reports/clean-code/findings-draft.md`; the reviewer consumes that draft and writes the report.
- Produces: the two deep-gear subagent roles.

One task: the reviewer's contract only makes sense against the analyzer's draft.

- [ ] **Step 1: Append the failing test**

```python
def test_deep_gear_agents_state_their_contracts():
    analyzer = read_skill_file("agents/analyzer.md")
    reviewer = read_skill_file("agents/reviewer.md")
    assert "read-only" in analyzer.lower()
    assert "findings-draft.md" in analyzer
    assert "clean-code-standard.md" in analyzer, "analyzer must judge against the standard"
    assert "report-template.md" in reviewer
    assert "clean-code-standard.md" in reviewer
    assert "verify" in reviewer.lower() and "prune" in reviewer.lower()
    assert "no code" in reviewer.lower() or "edit no code" in reviewer.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py::test_deep_gear_agents_state_their_contracts -q`
Expected: FAIL — files missing.

- [ ] **Step 3: Author `skills/clean-code/agents/analyzer.md`**

```markdown
# Role: clean-code analyzer (deep gear, read-only)

You draft candidate cleanliness findings for a diff, file, or module. You edit no
code. Your draft is not the final word — an independent reviewer re-verifies every
finding against the real code and prunes what doesn't hold up. So carry quotable
evidence, and flag borderline items honestly rather than self-censoring.

## Inputs (from the orchestrator)

- The scope (paths / the diff) and scope notes.
- `../../docs/clean-code-standard.md` — the rubric. **Read it first**; your findings
  and severities come from it (top-down by leverage), not your own taste.
- Output path: `docs/reports/clean-code/findings-draft.md`.

## Process

1. **Read for intent first** — understand what the code is trying to do.
2. **Walk the standard top-down** (highest-leverage principles first). For each
   candidate, check the principle's **"Where this bends"** note *before* filing —
   don't raise false-DRY merges, speculative abstraction, over-extraction, or the
   removal of good *why*-comments.
3. **One cross-file pass** for duplicated logic and Demeter train-wrecks.
4. **Defer structural issues up-ladder** — if a finding is really SRP/dependency
   direction (`/solid`), a pattern (`/gof`), domain modelling (`/ddd`), or the
   component graph (`/clean-architecture`), note it as a hand-off, not a fix.

## Output — `findings-draft.md`

One entry per finding:
```markdown
## [G<n>] <short imperative title>
- **Principle:** <the numbered standard principle>
- **Location:** `file:line` <all sites>
- **Evidence:** <quote the key lines>
- **Why it costs the reader:** <one or two sentences — not just the rule name>
- **Suggested severity:** <High|Medium|Low> **Confidence:** <high|medium|low>
```
End with a **Coverage** section: what you examined, what you skipped and why.

## Limits

- Prefer the few findings a human will act on; a clean review is high-signal.
- Read-only. Do not modify, format, or "quickly fix" anything.
```

- [ ] **Step 4: Author `skills/clean-code/agents/reviewer.md`**

```markdown
# Role: clean-code reviewer (independent verifier, report author)

You are the critic in a generator–critic pair. The analyzer's draft findings are
*candidates*; you produce a report a human can trust. Every finding you keep, you
personally verified against the current code. You **edit no code**.

## Inputs (from the orchestrator)

- `docs/reports/clean-code/findings-draft.md` — the draft.
- `../../docs/clean-code-standard.md` — the rubric (read first).
- `../references/report-template.md` — the exact output shape.
- Output: `docs/reports/clean-code/CLEAN-CODE-REPORT-<YYYY-MM-DD>.md`.

## Process

1. **Verify every draft finding.** Open the cited files at the cited lines; don't
   trust the analyzer's quotes or line numbers. For each: **Keep** (fix stale
   lines — accuracy is yours now), **Adjust** (real issue, wrong principle/severity
   — re-file), or **Prune** (doesn't hold, or hits a "Where this bends" — record
   the reason; never prune silently).
2. **Hunt what the analyzer missed** — its Coverage tells you where it didn't look;
   the classic misses are cross-file (duplication, Demeter). One deliberate sweep;
   it terminates by *writing* its outcome even when it adds nothing.
3. **Severity with the standard's rubric** (High/Medium/Low). When in doubt, down.
4. **Write the report** using `report-template.md` exactly. Keep the hand-offs
   up-ladder (`/solid`, `/gof`, `/ddd`, `/clean-architecture`) as a distinct
   section — they are not clean-code fixes.

## Quality bar

Ten findings a human acts on beat thirty they skim. If nothing meaningful is
wrong, say so plainly — never manufacture findings.
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py::test_deep_gear_agents_state_their_contracts -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/clean-code/agents/analyzer.md skills/clean-code/agents/reviewer.md tests/test_clean_code_skill_structure.py
git commit -m "feat(clean-code): deep-gear analyzer + reviewer roles"
```

---

## Task 5: `skills/clean-code/references/report-template.md`

**Files:**
- Create: `skills/clean-code/references/report-template.md`
- Modify: `tests/test_clean_code_skill_structure.py`

**Interfaces:**
- Consumes: `read_skill_file`.
- Produces: the deep-gear report shape. IDs `G1,G2,…`.

- [ ] **Step 1: Append the failing test**

```python
def test_report_template_has_the_expected_structure():
    text = read_skill_file("references/report-template.md")
    for marker in ["[G1]", "Principle", "Severity", "High", "Medium", "Low", "Hand-offs"]:
        assert marker in text, f"report-template.md missing: {marker}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py::test_report_template_has_the_expected_structure -q`
Expected: FAIL — file missing.

- [ ] **Step 3: Author `skills/clean-code/references/report-template.md`**

````markdown
# clean-code deep-review report template

The reviewer writes `docs/reports/clean-code/CLEAN-CODE-REPORT-<YYYY-MM-DD>.md` in
exactly this shape. IDs `G1,G2,…`, permanent once assigned. Angle brackets are
fill-slots.

```markdown
# Clean-code review — <scope> — <YYYY-MM-DD>

## Summary
- Scope: <paths / diff reviewed>, <N> files
- Findings: <n> High, <n> Medium, <n> Low
- Top items: <the 2–3 that matter most, one line each>

## Findings

### High
#### [G1] <short imperative title>
- **Principle:** <numbered standard principle>
- **Location:** `path/to/file.py:42` <all sites>
- **Evidence:** <quote the key lines>
- **Why it costs the reader:** <the concrete reader impact, not the rule name>
- **Suggestion:** <the concrete fix>
- **Severity:** High

### Medium
#### [M-style G<n>] ...

### Low
#### [G<n>] ...

## Hand-offs (not clean-code fixes)
- <structural issue> → `/solid` | `/gof` | `/ddd` | `/clean-architecture`, one line each

## Looks good
- <what is already clean and should be kept, incl. good why-comments>

## Reviewer notes
- Draft findings pruned as false positives: <finding → reason>, or "none"
- Areas not examined: <coverage gaps>
```
````

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py::test_report_template_has_the_expected_structure -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/clean-code/references/report-template.md tests/test_clean_code_skill_structure.py
git commit -m "feat(clean-code): deep-review report template"
```

---

## Task 6: Wire the substrate consumers

**Files:**
- Modify: `docs/refactor-agents/implementer.md`
- Modify: `skills/tdd/references/refactor-jobs.md`
- Modify: `tests/test_clean_code_skill_structure.py`

**Interfaces:**
- Consumes: `read_repo_file`; the standard created in Task 2 (its link target must already exist — it does).
- Produces: every applied refactor and every test-first refactor step cleans to the standard.

- [ ] **Step 1: Append the failing test**

```python
def test_substrate_consumers_link_the_standard():
    implementer = read_repo_file("docs/refactor-agents/implementer.md")
    refactor_jobs = read_repo_file("skills/tdd/references/refactor-jobs.md")
    assert "clean-code-standard.md" in implementer, "implementer role must link the standard"
    assert "clean-code-standard.md" in refactor_jobs, "tdd refactor step must link the standard"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py::test_substrate_consumers_link_the_standard -q`
Expected: FAIL — neither file links the standard yet.

- [ ] **Step 3: Edit `docs/refactor-agents/implementer.md`**

This file's relative links resolve from `docs/refactor-agents/`, so the standard
is `../clean-code-standard.md`. Immediately **after** the `## Inputs (from the
orchestrator)` list (before `## Per-recommendation loop`), insert this section:

```markdown
## Craft standard (applies to every rec)

The code the TDD refactor job produces follows
[../clean-code-standard.md](../clean-code-standard.md) — names, function/class
shape, error handling, comments. Clean-by-construction is the point: a refactor
that fixes a structural smell but leaves the touched code sloppy is not done. Pass
the standard through to the refactor job as part of each rec's `change` context.
```

- [ ] **Step 4: Edit `skills/tdd/references/refactor-jobs.md`**

Open the file and read it. Find the section that describes the **refactor step**
of the job (the green→refactor phase, where the code is cleaned up after tests
pass). Append this sentence to that section (adjust the relative path only if the
file's depth differs — from `skills/tdd/references/` the standard is
`../../../docs/clean-code-standard.md`):

```markdown
When cleaning up in the refactor step, clean **to the standard**:
[../../../docs/clean-code-standard.md](../../../docs/clean-code-standard.md)
(names, small functions, no hidden side effects, good *why*-comments). This is
what makes every lens's applied refactor come out clean by construction.
```

- [ ] **Step 5: Run to verify it passes + links resolve**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py::test_substrate_consumers_link_the_standard tests/test_skill_integrity.py::test_relative_markdown_links_resolve -q`
Expected: PASS (both — the new `../clean-code-standard.md` and `../../../docs/clean-code-standard.md` links resolve because Task 2 created the target).

- [ ] **Step 6: Commit**

```bash
git add docs/refactor-agents/implementer.md skills/tdd/references/refactor-jobs.md tests/test_clean_code_skill_structure.py
git commit -m "feat(clean-code): wire implementer role + tdd refactor step to the standard"
```

---

## Task 7: Reports convention → `docs/reports/<lens>/`

**Files:**
- Modify: `docs/refactor-workflow.md` (Phase 0 report-dir step)
- Modify: `skills/solid/**`, `skills/gof/**`, `skills/ddd/**` (report-path references)
- Modify: `.gitignore`
- Modify: `tests/test_clean_code_skill_structure.py`

**Interfaces:**
- Produces: every lens writes to `docs/reports/<lens>/` (git-excluded); no bare `*-reports/` remains.

- [ ] **Step 1: Append the failing test**

```python
def test_reports_convention_points_at_docs_reports():
    workflow = read_repo_file("docs/refactor-workflow.md")
    assert "docs/reports/" in workflow, "refactor-workflow Phase 0 must use docs/reports/<lens>/"
    gitignore = read_repo_file(".gitignore")
    assert "docs/reports/" in gitignore, ".gitignore must exclude docs/reports/"
    # no lens SKILL still points at the old bare report dirs
    old_dirs = {
        "skills/solid/SKILL.md": "solid-reports/",
        "skills/gof/SKILL.md": "gof-reports/",
        "skills/ddd/SKILL.md": "ddd-reports/",
    }
    offenders = [path for path, old in old_dirs.items() if old in read_repo_file(path)]
    assert not offenders, f"these still reference the old bare report dir: {offenders}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py::test_reports_convention_points_at_docs_reports -q`
Expected: FAIL — the workflow and SKILLs still use bare `*-reports/`.

- [ ] **Step 3: Update `docs/refactor-workflow.md` Phase 0**

Find the Phase 0 "Report dir" step (it currently reads roughly: *"create
`<lens>-reports/` in the target project and git-exclude it via `.git/info/exclude`"*).
Replace it with:

```markdown
3. **Report dir**: create `docs/reports/<lens>/` in the target project (e.g.
   `docs/reports/solid/`) and git-exclude it — add `docs/reports/` to
   `.git/info/exclude` if the repo is a git repo and doesn't already ignore it.
   Reports are ephemeral working artifacts by default; the user may choose to
   commit a final report as a living doc at the end.
```

Also update the Phase 2 output-path reference in the same file from
`<lens>-reports/<LENS>-REFACTOR-<YYYY-MM-DD>.md` to
`docs/reports/<lens>/<LENS>-REFACTOR-<YYYY-MM-DD>.md`.

- [ ] **Step 4: Update the three lens skills' report paths**

Enumerate the sites:
```bash
grep -rln "solid-reports/\|gof-reports/\|ddd-reports/" skills/solid skills/gof skills/ddd
```
In each matched file, mechanically replace the bare dir with the `docs/reports/`
form: `solid-reports/` → `docs/reports/solid/`, `gof-reports/` → `docs/reports/gof/`,
`ddd-reports/` → `docs/reports/ddd/`. **Leave `ddd`'s `docs/domain/` references
untouched** — that is a deliverable, not a report. Then verify none remain:
```bash
grep -rn "solid-reports/\|gof-reports/\|ddd-reports/" skills/solid skills/gof skills/ddd docs/refactor-workflow.md
```
Expected: no matches.

- [ ] **Step 5: Update `.gitignore`**

Replace the existing SOLID-reports block:
```
# SOLID skill reports (regenerable)
solid-reports/
```
with:
```
# Lens reports (regenerable working artifacts)
docs/reports/
```

- [ ] **Step 6: Run to verify it passes + guards stay green**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py::test_reports_convention_points_at_docs_reports tests/test_skill_integrity.py -q`
Expected: PASS (convention updated; links still resolve; version mirrors intact).

- [ ] **Step 7: Commit**

```bash
git add docs/refactor-workflow.md skills/solid skills/gof skills/ddd .gitignore tests/test_clean_code_skill_structure.py
git commit -m "refactor: consolidate lens reports under docs/reports/<lens>/ (git-excluded)"
```

---

## Task 8: Trigger + behaviour evals

**Files:**
- Create: `evals/clean-code-evals.json`
- Modify: `tests/test_clean_code_skill_structure.py`

**Interfaces:**
- Consumes: `REPO_ROOT`, `json`.
- Produces: eval cases mirroring `evals/ddd-evals.json`'s schema (`skill_name` + `evals[]` with `id`, `skill`, `prompt`, `expected_output`, `assertions`).

- [ ] **Step 1: Append the failing test**

```python
def test_clean_code_evals_cover_substrate_and_both_gears():
    evals_path = REPO_ROOT / "evals" / "clean-code-evals.json"
    assert evals_path.is_file(), "evals/clean-code-evals.json missing"
    document = json.loads(evals_path.read_text())
    assert document["skill_name"] == "clean-code"
    cases = document["evals"]
    assert len(cases) >= 4, "want at least 4 eval cases"
    for case in cases:
        for field in ["id", "skill", "prompt", "expected_output", "assertions"]:
            assert field in case, f"eval case {case.get('id')} missing {field}"
        assert isinstance(case["assertions"], list) and case["assertions"]
    blob = json.dumps(document).lower()
    assert "quick" in blob and "deep" in blob            # both gears
    assert "clean-code-standard" in blob                 # single source of truth
    assert "defer" in blob or "hand off" in blob or "up-ladder" in blob  # non-overlap
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py::test_clean_code_evals_cover_substrate_and_both_gears -q`
Expected: FAIL — file missing.

- [ ] **Step 3: Author `evals/clean-code-evals.json`**

```json
{
  "skill_name": "clean-code",
  "evals": [
    {
      "id": 1,
      "skill": "clean-code",
      "prompt": "Quick clean-code pass on this diff before I commit?",
      "expected_output": "Uses the quick gear: one read-through against docs/clean-code-standard.md, findings reported inline with file:line and severity, no subagents and no report file, respecting the 'where this bends' notes.",
      "assertions": [
        "Reads docs/clean-code-standard.md as the rubric",
        "Uses the quick gear for a small diff (inline findings, no report file, no subagents)",
        "Reports each finding with file:line, the principle, the reader-cost, a concrete suggestion, and a severity",
        "Honours the 'where this bends' notes (no false-DRY, speculative-abstraction, or over-extraction findings)",
        "Says so plainly if nothing meaningful is wrong instead of manufacturing findings"
      ]
    },
    {
      "id": 2,
      "skill": "clean-code",
      "prompt": "Do a thorough clean-code review of the whole payments module.",
      "expected_output": "Uses the deep gear: two-stage analyzer->reviewer verification, writing docs/reports/clean-code/CLEAN-CODE-REPORT-<date>.md via the report template; apply stays opt-in.",
      "assertions": [
        "Uses the deep gear for a module-sized scope",
        "Dispatches a read-only analyzer then an independent reviewer that re-verifies every finding",
        "Creates git-excluded docs/reports/clean-code/ and writes the report using references/report-template.md",
        "Does not apply changes unless explicitly asked (review stops at findings)"
      ]
    },
    {
      "id": 3,
      "skill": "clean-code",
      "prompt": "This 400-line OrderService class is a mess — is it clean?",
      "expected_output": "Flags line-level craft, but recognises the god-class/SRP problem as structural and defers it up-ladder to /solid rather than solving architecture under the clean-code lens.",
      "assertions": [
        "Reports line-level craft findings (names, long functions, comments) against the standard",
        "Identifies the single-responsibility / god-class problem as structural",
        "Defers the structural fix up-ladder to /solid (and names /gof, /ddd, or /clean-architecture where relevant) instead of redesigning under clean-code",
        "Keeps the hand-offs as a distinct section, not clean-code fixes"
      ]
    },
    {
      "id": 4,
      "skill": "clean-code",
      "prompt": "We're doing a SOLID refactor — will the extracted classes end up clean?",
      "expected_output": "Explains the substrate role: because the shared implementer role and tdd link docs/clean-code-standard.md, code produced by any lens's refactor is clean by construction — no separate clean-code invocation is needed for that.",
      "assertions": [
        "Explains that clean-code is a substrate linked by the shared implementer role and tdd",
        "States that /solid, /gof, and /clean-architecture refactors come out clean by construction",
        "Points at docs/clean-code-standard.md as the single source of truth consumers link (never copy)",
        "Distinguishes the ambient substrate role from the invoked standalone review"
      ]
    }
  ]
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_clean_code_skill_structure.py::test_clean_code_evals_cover_substrate_and_both_gears -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/clean-code-evals.json tests/test_clean_code_skill_structure.py
git commit -m "test(clean-code): trigger + behaviour evals for substrate and both gears"
```

---

## Task 9: Full-suite green + finish

**Files:** none (verification + handoff).

- [ ] **Step 1: Run the whole repo test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — all pre-existing tests (now including the Task 1 mirror fix) plus the new `test_clean_code_skill_structure.py` tests. If anything unrelated fails, confirm it also failed on `main` before reporting; do not "fix" unrelated code.

- [ ] **Step 2: Confirm the clean-code skill directory is complete**

Run: `find skills/clean-code -type f | sort`
Expected exactly:
```
skills/clean-code/SKILL.md
skills/clean-code/agents/analyzer.md
skills/clean-code/agents/reviewer.md
skills/clean-code/references/report-template.md
```

- [ ] **Step 3: Confirm the standard is the single source of truth**

Run: `grep -rl "clean-code-standard.md" docs/refactor-agents/implementer.md skills/tdd/references/refactor-jobs.md skills/clean-code/`
Expected: the implementer role, the tdd refactor-jobs reference, and the clean-code SKILL + agents all appear — every consumer links the one standard.

- [ ] **Step 4: Hand off to Plan 2 (never auto-run)**

Plan 1 is complete on `clean-architecture/skills`. The next unit is **Plan 2 —
`clean-architecture` lens + overlap-hub migration + manifest registration**
(`docs/superpowers/plans/2026-07-20-clean-architecture-lens.md`, written
separately). Do **not** open a PR yet — both plans land together. Offer the user:
continue to Plan 2, or review Plan 1's diff first.

- [ ] **Step 5: Offer to capture to the memory brain (never silently)**

Offer to record the durable decision that `clean-code` is now a shared substrate
(canonical `docs/clean-code-standard.md`, consumed by the implementer role + tdd;
thin two-gear review; reports under `docs/reports/<lens>/`) via the `/memory`
protocol.

---

## Self-Review (completed during authoring)

**Spec coverage:**
- clean-code hybrid substrate: canonical standard + thin two-gear review → Tasks 2, 3. ✓
- Standard consumed by implementer role + tdd (clean by construction) → Task 6 + eval 4. ✓
- 3 missing chapters (Boundaries/learning tests, Simple Design 4 rules, Smells catalogue) → Task 2 (`test_standard_has_the_fifteen_principles_and_three_new_chapters`). ✓
- Two-stage verified deep gear + report → Tasks 4, 5 + eval 2. ✓
- Quick inline gear → Task 3 + eval 1. ✓
- Defer structural findings up-ladder (non-overlap) → Task 3, Task 4 analyzer, Task 5 hand-offs + eval 3. ✓
- Apply opt-in only → Task 3. ✓
- Reports → `docs/reports/<lens>/` git-excluded → Task 7. ✓
- clean-code version 0.2.0; three version mirrors intact (baseline fix) → Tasks 1, 3. ✓

**Placeholder scan:** the `<...>` angle brackets inside the report templates are intentional runtime fill-slots (same convention as `ddd`'s template), not plan placeholders. The two `<!-- PORT … -->` markers in Task 2 are precise move-instructions with exact source line ranges (`skills/clean-code/SKILL.md:47–252`), not vague TODOs — the content already exists verbatim in the repo and is copied, not invented. No TBD/TODO in the plan.

**Type/name consistency:** `read_repo_file` / `read_skill_file` / `parse_frontmatter` / `REPO_ROOT` / `CLEAN_CODE_STANDARD` are defined once in Task 2 and reused verbatim in Tasks 3–8. Marker strings asserted by tests (`clean-code-standard.md`, `docs/reports/`, `[G1]`, `Boundaries`, `Simple Design`, `Smells & Heuristics`, version `0.2.0`) each appear verbatim in the authored files. Test command `.venv/bin/python -m pytest` is used in every run step.
```
