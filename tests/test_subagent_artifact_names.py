"""Guard the filenames subagents are told to write (issue #112).

It is a filename check and nothing else — not a permission, not a hook, and
there is no ask-the-user path. Claude Code's ``Write`` tool hard-denies any
subagent write whose basename starts with
``REPORT``/``SUMMARY``/``FINDINGS``/``ANALYSIS`` (case-insensitive, ``.md``
only)::

    if (r.agentId && /^(REPORT|SUMMARY|FINDINGS|ANALYSIS).*\\.md$/i.test(basename))
      return {result: false, message: "Subagents should return findings as
              text, not write report files. ..."}

That is what blocked the old ``findings-draft.md`` hand-off: the analyzer
could never write it, so it returned the whole draft as chat text and the
orchestrator re-emitted it.

These tests pin the workaround (the artifact is ``draft-findings.md``) so a
future rename can't silently walk back into the guard.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
DOCS_DIR = REPO_ROOT / "docs"

# The harness guard, transcribed from the Write tool's validateInput.
BLOCKED_BASENAME = re.compile(r"^(REPORT|SUMMARY|FINDINGS|ANALYSIS).*\.md$", re.I)

# "/" is included so a reference written as a path (e.g. `docs/reports/x.md`)
# is captured whole; the rsplit in blocked_names_in() then reduces it to the
# basename the harness actually checks.
MARKDOWN_REF = re.compile(r"[A-Za-z0-9_/<>{}.-]+\.md")

# Templates and rubrics agents only ever *read*. Reads are unguarded, so a
# blocked-looking name here is harmless — it is never a Write target.
READ_ONLY_ARTIFACTS = {"report-template.md"}

# Frozen eval snapshots and narrative plans/specs record history, including the
# pre-fix name. They drive no live dispatch. Matched on the repo-relative path
# and on path *parts*, not on an absolute-path substring — a checkout under a
# directory containing "-workspace" (or anything else) must not silently empty
# the scan.
EXCLUDED_DIRS = ("docs/superpowers", "docs/reports")
EXCLUDED_SUFFIXES = ("-workspace",)


def live_contracts() -> list[Path]:
    """Every doc that a running lens actually dispatches from.

    Scope is deliberately docs/ and skills/ *.md only — the trees a running
    lens actually dispatches subagents from. Root README.md, evals/, hooks/,
    and scripts/ are out of scope for this scan (see task 4 for the one known
    evals/ instance).
    """
    candidates = [*DOCS_DIR.rglob("*.md"), *SKILLS_DIR.rglob("*.md")]
    contracts = []
    for path in candidates:
        rel = path.relative_to(REPO_ROOT)
        excluded = rel.as_posix().startswith(EXCLUDED_DIRS) or any(
            part.endswith(EXCLUDED_SUFFIXES) for part in rel.parts
        )
        if not excluded:
            contracts.append(path)
    return contracts


def prose_lines(path: Path) -> list[str]:
    """All lines in ``path``. Blockquotes are not excluded: this repo uses them
    for its strongest normative callouts (e.g. the guard note in
    docs/refactor-workflow.md), so "blockquote = non-normative" does not hold
    here."""
    return path.read_text(encoding="utf-8").splitlines()


def blocked_names_in(path: Path) -> list[str]:
    """Every blocked basename referenced in ``path``, empty if none."""
    offenders = []
    for line in prose_lines(path):
        for basename in MARKDOWN_REF.findall(line):
            basename = basename.rsplit("/", 1)[-1]
            if basename in READ_ONLY_ARTIFACTS:
                continue
            if BLOCKED_BASENAME.match(basename):
                offenders.append(basename)
    return offenders


def test_no_live_contract_names_a_blocked_write_target():
    offenders = []
    for path in live_contracts():
        for basename in blocked_names_in(path):
            offenders.append(f"{path.relative_to(REPO_ROOT)} → {basename}")

    assert not offenders, (
        "These artifact names start with REPORT/SUMMARY/FINDINGS/ANALYSIS, so a "
        "subagent's Write of them is hard-denied by the harness. Put a "
        "distinguishing word first (see docs/refactor-workflow.md):\n  "
        + "\n  ".join(sorted(set(offenders)))
    )


def test_live_contracts_scans_something():
    """A scanner that scans nothing must never be green."""
    assert live_contracts()


def test_blocked_names_in_flags_blocked_basename(tmp_path):
    path = tmp_path / "contract.md"
    path.write_text("Write your findings to `FINDINGS-2026-07-29.md`.\n")
    assert blocked_names_in(path) == ["FINDINGS-2026-07-29.md"]


def test_blocked_names_in_ignores_safe_basenames(tmp_path):
    path = tmp_path / "contract.md"
    path.write_text("Write the hand-off to `draft-findings.md`.\n")
    assert blocked_names_in(path) == []


def test_blocked_basename_matches_every_harness_word():
    """The regex must deny all four words the harness blocks — not just some."""
    for word in ("REPORT", "SUMMARY", "FINDINGS", "ANALYSIS"):
        assert BLOCKED_BASENAME.match(f"{word}-2026-07-29.md")
        assert BLOCKED_BASENAME.match(f"{word.lower()}-draft.md")


def test_analyzer_reviewer_handoff_is_draft_findings():
    """The hand-off name is load-bearing, not cosmetic — pin it explicitly."""
    workflow = "\n".join(prose_lines(DOCS_DIR / "refactor-workflow.md"))
    assert "draft-findings.md" in workflow
    assert "findings-draft.md" not in workflow


def test_dated_lens_report_name_clears_the_guard():
    """`<LENS>-REPORT-<date>.md` is safe only because the lens name comes first."""
    lenses = ("SOLID", "GOF", "DDD", "CLEAN-CODE", "CLEAN-ARCHITECTURE", "TEST-QUALITY")
    for lens in lenses:
        assert not BLOCKED_BASENAME.match(f"{lens}-REPORT-<YYYY-MM-DD>.md")
    # The guard is real: the same name without the lens prefix would be denied.
    assert BLOCKED_BASENAME.match("REPORT-<YYYY-MM-DD>.md")
