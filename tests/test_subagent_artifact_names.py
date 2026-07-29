"""Guard the filenames subagents are told to write (issue #112).

Claude Code's ``Write`` tool hard-denies any subagent write whose basename
starts with ``REPORT``/``SUMMARY``/``FINDINGS``/``ANALYSIS`` (case-insensitive,
``.md`` only)::

    if (r.agentId && /^(REPORT|SUMMARY|FINDINGS|ANALYSIS).*\\.md$/i.test(basename))
      return {result: false, message: "Subagents should return findings as
              text, not write report files. ..."}

It is a filename check and nothing else — not a permission, not a hook, and
there is no ask-the-user path. That is what blocked the old
``findings-draft.md`` hand-off: the analyzer could never write it, so it
returned the whole draft as chat text and the orchestrator re-emitted it.

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

MARKDOWN_REF = re.compile(r"[A-Za-z0-9_<>{}.-]+\.md")

# Templates and rubrics agents only ever *read*. Reads are unguarded, so a
# blocked-looking name here is harmless — it is never a Write target.
READ_ONLY_ARTIFACTS = {"report-template.md"}

# Frozen eval snapshots and narrative plans/specs record history, including the
# pre-fix name. They drive no live dispatch.
EXCLUDED_DIRS = ("-workspace", "/docs/superpowers/", "/docs/reports/")


def live_contracts() -> list[Path]:
    """Every doc that a running lens actually dispatches from."""
    candidates = [*DOCS_DIR.rglob("*.md"), *SKILLS_DIR.rglob("*.md")]
    return [
        path
        for path in candidates
        if not any(marker in path.as_posix() for marker in EXCLUDED_DIRS)
    ]


def prose_lines(path: Path) -> list[str]:
    """Contract lines only. Blockquotes are excluded: the note documenting this
    very guard has to spell out the forbidden names to warn about them."""
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith(">")
    ]


def test_no_live_contract_names_a_blocked_write_target():
    offenders = []
    for path in live_contracts():
        for line in prose_lines(path):
            for basename in MARKDOWN_REF.findall(line):
                basename = basename.rsplit("/", 1)[-1]
                if basename in READ_ONLY_ARTIFACTS:
                    continue
                if BLOCKED_BASENAME.match(basename):
                    offenders.append(f"{path.relative_to(REPO_ROOT)} → {basename}")

    assert not offenders, (
        "These artifact names start with REPORT/SUMMARY/FINDINGS/ANALYSIS, so a "
        "subagent's Write of them is hard-denied by the harness. Put a "
        "distinguishing word first (see docs/refactor-workflow.md):\n  "
        + "\n  ".join(sorted(set(offenders)))
    )


def test_analyzer_reviewer_handoff_is_draft_findings():
    """The hand-off name is load-bearing, not cosmetic — pin it explicitly."""
    workflow = "\n".join(prose_lines(DOCS_DIR / "refactor-workflow.md"))
    assert "draft-findings.md" in workflow
    assert "findings-draft.md" not in workflow


def test_dated_lens_report_name_clears_the_guard():
    """`<LENS>-REPORT-<date>.md` is safe only because the lens name comes first."""
    for lens in ("SOLID", "GOF", "DDD", "CLEAN-CODE", "TEST-QUALITY"):
        assert not BLOCKED_BASENAME.match(f"{lens}-REPORT-2026-07-29.md")
    # The guard is real: the same name without the lens prefix would be denied.
    assert BLOCKED_BASENAME.match("REPORT-2026-07-29.md")
