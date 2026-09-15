"""All six lenses ship the same per-language trio (issue #129).

Four of six did. `clean-code` and `test-quality` shipped none — which is exactly
backwards for the two of them:

- `clean-code` is the **line-level craft** lens. That is the most
  language-specific material in the toolkit, not the least: a record accessor, a
  builder, a checked-exception boundary and a sealed hierarchy all read as clean
  in Java and as ceremony in Python.
- `test-quality` audits test suites, and test idiom is equally language-bound —
  JUnit 5 lifecycle and `@ParameterizedTest` vs pytest fixtures and
  `parametrize` vs Vitest's `it.each` and its floating-promise failure mode.

The convention they now follow is the one in `docs/refactor-workflow.md`:
**adding a language is adding a file, never editing a SKILL body.** These tests
pin that the files exist, that the agents load them by the `<language>.md`
pattern rather than hardcoding one stack, and — the part that stops the next
drift — that no lens is missing a language the others have.
"""

from pathlib import Path

import pytest

from lens_roster import (
    STRUCTURAL_STEMS,
    SUPPORTED_LANGUAGES,
    discovered_lenses,
    language_lenses,
    lenses_shipping,
    shared_reference_stems,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS = REPO_ROOT / "skills"

# Discovered, never transcribed. The hardcoded six-lens tuple that used to live
# here is why the seventh lens was silently skipped by every guard below.
LENSES = tuple(language_lenses())
LANGUAGES = SUPPORTED_LANGUAGES


@pytest.mark.parametrize("lens", LENSES)
@pytest.mark.parametrize("language", LANGUAGES)
def test_every_lens_ships_every_language(lens, language):
    reference = SKILLS / lens / "references" / f"{language}.md"

    assert reference.is_file(), f"{lens} ships no references/{language}.md"


@pytest.mark.parametrize("lens", LENSES)
def test_no_lens_is_missing_a_language_the_others_have(lens):
    """The drift guard, and it used to be vacuous.

    It filtered each lens's shipped stems THROUGH the hardcoded language tuple
    before comparing, so it could only ever detect a language somebody had also
    remembered to add to the tuple. Adding `go.md` to five lenses and forgetting
    the sixth passed green. The roster is discovered now, and the half-rolled-out
    case has its own test below.
    """
    shipped = {
        reference.stem
        for reference in (SKILLS / lens / "references").glob("*.md")
        if reference.stem in LANGUAGES
    }

    assert shipped == set(LANGUAGES), f"{lens} ships {sorted(shipped)}"


def test_the_roster_this_file_iterates_is_not_empty():
    """A guard on the guard: discovery returning nothing would make every
    parametrized test above vacuously pass, which is the failure mode the
    hardcoded tuple had in a different costume."""
    assert len(LENSES) >= 6
    assert len(discovered_lenses()) > len(LENSES), "the dialect lens is missing"


def test_a_half_rolled_out_language_is_caught():
    """The case the old guard could not see: a reference two or more lenses ship
    that is not a declared language. That is a language added to some lenses and
    missing from the rest — exactly the state this file exists to prevent, and
    invisible to a test that iterates the declared set."""
    undeclared = {
        stem: lenses
        for stem, lenses in shared_reference_stems().items()
        if stem not in SUPPORTED_LANGUAGES and stem not in STRUCTURAL_STEMS
    }

    assert not undeclared, (
        "shared reference(s) that are neither a declared language nor lens "
        f"scaffolding — add to SUPPORTED_LANGUAGES or finish the rollout: {undeclared}"
    )


def test_every_declared_language_reaches_every_language_lens():
    """Stated from the language's side rather than the lens's, so a language
    shipped by only some lenses fails with the gap named."""
    for language in SUPPORTED_LANGUAGES:
        assert lenses_shipping(language) == language_lenses(), (
            f"{language}.md is shipped by {lenses_shipping(language)}, "
            f"not by every language lens"
        )


@pytest.mark.parametrize("lens", ["clean-code", "test-quality"])
def test_the_new_references_are_content_not_placeholders(lens):
    """A stub file satisfies the existence test above while teaching nothing.
    Each reference has to carry real per-language material and — the part that
    keeps this lens honest — a statement of where the rule bends in that
    language."""
    for language in LANGUAGES:
        text = (SKILLS / lens / "references" / f"{language}.md").read_text()

        assert len(text.splitlines()) > 40, f"{lens}/{language}.md is a stub"
        assert (
            "bend" in text.lower()
            or "must not be filed" in text.lower()
            or "not be filed" in text.lower()
        ), f"{lens}/{language}.md never says where the rule does not apply"


class TestTheAgentsActuallyLoadThem:
    """A reference nothing reads is a file, not a capability."""

    @pytest.mark.parametrize("role", ["analyzer", "reviewer"])
    def test_clean_code_agents_load_by_the_language_pattern(self, role):
        text = (SKILLS / "clean-code/agents" / f"{role}.md").read_text()

        assert "<language>.md" in text
        # Hardcoding one stack is the thing the convention exists to prevent.
        assert "python.md" in text and "java.md" in text

    @pytest.mark.parametrize("role", ["analyzer", "reviewer"])
    def test_test_quality_agents_load_by_the_language_pattern(self, role):
        text = (SKILLS / "test-quality/agents" / f"{role}.md").read_text()

        assert "<language>.md" in text


class TestTestQualityCitesTddRatherThanForkingIt:
    """#129's cheaper path: `tdd` already ships the language adapters, and this
    lens audits the suites that skill writes. A second standard would be a
    second thing to drift."""

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_each_reference_points_at_the_tdd_adapter(self, language):
        text = (SKILLS / "test-quality/references" / f"{language}.md").read_text()

        assert "tdd/references/" in text

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_each_reference_is_the_audit_view_not_the_writing_standard(self, language):
        """What distinguishes this file from `tdd`'s: it says what the SMELL
        looks like here, including what is ordinary in this language and must
        not be filed."""
        text = (SKILLS / "test-quality/references" / f"{language}.md").read_text()

        assert "rubric.md" in text
        assert "mock" in text.lower()


class TestCleanCodeCoversTheLanguageSpecificCraft:
    def test_python_covers_the_traps_that_are_defects_not_style(self):
        text = (SKILLS / "clean-code/references/python.md").read_text()

        assert "mutable default" in text.lower()
        assert "bare `except:`" in text or "bare except" in text.lower()

    def test_typescript_covers_the_failure_mode_that_language_owns(self):
        text = (SKILLS / "clean-code/references/typescript.md").read_text()

        assert "any" in text
        assert "floating promise" in text.lower()

    def test_java_warns_against_writing_2005_java(self):
        """The failure mode of applying clean-code literally in Java is
        ceremony: a factory, an interface and an abstract base where a record
        and a switch would do."""
        text = (SKILLS / "clean-code/references/java.md").read_text()

        assert "record" in text.lower()
        assert "FooImpl" in text or "IFoo" in text
        assert "Boot 4" in text
