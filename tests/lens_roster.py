"""The lens roster, DISCOVERED from the filesystem rather than transcribed.

Nine of the fifteen findings in the 2026-09-16 review were one shape: a
mechanism built correctly, with the roster it operates on hand-enumerated in
prose beside it. "Six lenses" survived in four separate files after the seventh
shipped — `docs/report-contract.md`, `docs/refactor-workflow.md`, the
consolidator's precedence ladder, and two test modules whose hardcoded tuples
meant the new lens was silently skipped by every guard hanging off them.

Adding the seventh lens should have been one edit. It was five, four of them
missed, and the suite stayed green.

So the roster lives here once, derived from what is actually on disk. Prose
cannot glob, so a document that must name the lenses still names them — but a
test compares what it names against this, and fails when they disagree. That
retires the drift class rather than its instances.

**A lens is a skill that ships both halves of the generator/critic pair**:
`agents/analyzer.md` and `agents/reviewer.md`. That is what makes it a lens
rather than a skill with agents — the `code-quality` umbrella ships only
`agents/consolidator.md` and correctly excludes itself, with no exception list
to maintain.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"


def discovered_lenses():
    """Every lens the repo actually ships, sorted. The single source of truth."""
    return sorted(
        skill_directory.name
        for skill_directory in SKILLS_DIR.iterdir()
        if skill_directory.is_dir()
        and (skill_directory / "agents" / "analyzer.md").is_file()
        and (skill_directory / "agents" / "reviewer.md").is_file()
    )


# The ID prefix each lens uses in a finding code. It is the directory name for
# every lens but one: `clean-architecture` writes `clean-arch/` because the full
# name made every ID in the consolidated report unreadably long. That exception
# is DATA here rather than a special case scattered through the guards.
ID_PREFIX_OVERRIDES = {"clean-architecture": "clean-arch"}


def id_prefix(lens_name):
    return ID_PREFIX_OVERRIDES.get(lens_name, lens_name)


def discovered_id_prefixes():
    return sorted(id_prefix(lens_name) for lens_name in discovered_lenses())


# The languages the lens family supports. Declared ONCE, here -- which language
# set to support is a decision, not something to infer, and the drift risk was
# never the declaring, it was declaring it in five places.
SUPPORTED_LANGUAGES = ("python", "typescript", "java")


def lenses_shipping(reference_stem):
    """Which lenses ship `<reference_stem>.md`. Sorted."""
    return sorted(
        lens_name
        for lens_name in discovered_lenses()
        if (SKILLS_DIR / lens_name / "references" / f"{reference_stem}.md").is_file()
    )


def shared_reference_stems():
    """Reference stems that MORE THAN ONE lens ships.

    The drift detector for the language set above. A stem two or more lenses
    carry is family-wide material -- a language, in practice -- so one that is
    not in `SUPPORTED_LANGUAGES` is a language half-rolled-out: added to some
    lenses, missing from others, and invisible to a guard that only iterates the
    declared tuple. A stem exactly one lens ships is lens-specific by definition
    (`cqrs`, `sagas`, `gherkin`, `strategic`) and is not the family's business.
    """
    counts = {}
    for lens_name in discovered_lenses():
        for reference in (SKILLS_DIR / lens_name / "references").glob("*.md"):
            counts.setdefault(reference.stem, []).append(lens_name)
    return {stem: lenses for stem, lenses in counts.items() if len(lenses) > 1}


# The scaffolding every lens carries. Not languages, and enumerable precisely
# because they are the lens shape itself rather than an open-ended set.
STRUCTURAL_STEMS = frozenset(
    {"report-template", "rubric", "principles", "patterns", "html-report"}
)

# Lenses whose variation axis is NOT the language. `acceptance-quality` varies by
# DIALECT (Gherkin first, others as files), so it ships `gherkin.md` and no
# `python.md` — correct, and it must not read as a missing language. Stated here
# so the exemption has a reason attached instead of living as an off-by-one in a
# hardcoded tuple.
DIALECT_LENSES = frozenset({"acceptance-quality"})


def language_lenses():
    """Lenses that vary by language, and so must ship the full language trio."""
    return [
        lens_name
        for lens_name in discovered_lenses()
        if lens_name not in DIALECT_LENSES
    ]
