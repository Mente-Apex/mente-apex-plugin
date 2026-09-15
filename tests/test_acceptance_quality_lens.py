"""The seventh lens: the acceptance layer as a subject (issue #122).

Six lenses graded the code and its unit suite. Nothing graded the scenarios
above them — and that is the layer with a different reader.

Unit and integration suites are largely left to the agent: nobody reads a
thousand unit tests, they are trusted because they are green. The acceptance
layer is the one **a human reads occasionally, and cold** — onboarding, a
stakeholder asking what the system does, a failure where somebody has to decide
whether the test or the behaviour is wrong.

That reader is what the whole rubric is calibrated to, and what these tests
mostly pin. The rest is the carve: `atdd` builds acceptance suites, this lens
audits one that exists, and neither does the other's job.
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LENS = REPO_ROOT / "skills" / "acceptance-quality"
UMBRELLA = REPO_ROOT / "skills" / "code-quality" / "SKILL.md"
HUB = REPO_ROOT / "docs" / "lens-overlap.md"


def read(relative_path):
    return (LENS / relative_path).read_text(encoding="utf-8")


def flat(relative_path):
    """The file with runs of whitespace collapsed to single spaces.

    These are prose files, wrapped at ~88 columns by convention, so any phrase
    long enough to be worth pinning is liable to straddle a line break. Asserting
    against the wrapped form pins the WRAPPING, which is not the contract and
    which reflows the moment a word changes upstream of it.
    """
    return " ".join(read(relative_path).split())


class TestTheLensExistsAndIsShaped:
    @pytest.mark.parametrize(
        "artifact",
        [
            "SKILL.md",
            "agents/analyzer.md",
            "agents/reviewer.md",
            "references/rubric.md",
            "references/gherkin.md",
            "references/report-template.md",
        ],
    )
    def test_it_ships_what_a_lens_ships(self, artifact):
        assert (LENS / artifact).is_file(), f"acceptance-quality ships no {artifact}"

    def test_its_agents_delegate_like_every_other_lens(self):
        """#131's rule applies to a new lens from day one, or the bimodality is
        back the moment it is added."""
        assert "refactor-agents/analyzer.md" in read("agents/analyzer.md")
        assert "refactor-agents/reviewer.md" in read("agents/reviewer.md")

    def test_it_declares_a_version(self):
        """That it HAS one, not which one — pinning the number here is the same
        transcribe-don't-derive mistake this branch is about, and the eval-stamp
        guard already checks the value against its eval set."""
        assert re.search(r'^\s+version: "\d+\.\d+\.\d+"', read("SKILL.md"), re.M)


class TestItIsCalibratedToTheColdOccasionalReader:
    """The judgement that makes this lens different from a unit-test lens."""

    def test_the_skill_says_who_reads_this_layer_and_how(self):
        text = read("SKILL.md")

        assert "occasionally" in text
        assert "cold" in text
        assert "left to the agent" in text

    def test_the_rubric_leads_with_the_cold_read_test(self):
        """It is applied to every finding, so it comes before the six areas
        rather than sitting among them."""
        text = read("references/rubric.md")

        assert "## The cold-read test" in text
        assert text.index("cold-read test") < text.index("## 1. Spec-as-spec")

    def test_passing_is_not_the_bar(self):
        """A scenario can run perfectly, cover real behaviour, and still have
        failed at the one job this layer has."""
        text = read("references/rubric.md")

        assert "Passing is not the bar here; being read is" in text

    def test_a_scenario_that_pins_nothing_is_critical(self):
        text = read("references/rubric.md")

        assert "decoration that reports green" in text

    def test_coverage_outranks_craft(self):
        """The failure only this lens can see: a unit suite cannot know what
        was agreed."""
        text = read("references/rubric.md")

        assert "Coverage outranks craft" in text

    def test_craft_that_costs_the_reader_nothing_is_minor_or_nothing(self):
        """Without this the lens becomes thirty wording nits, which spends the
        credibility needed for the finding that mattered."""
        text = read("references/rubric.md")

        assert "cost a cold reader nothing" in text
        assert "nobody opens twice" in text

    def test_the_reviewer_re_runs_the_cold_read_itself(self):
        """The analyzer stops being a cold reader after the third file. That
        drift is why this lens has an independent reviewer at all."""
        text = read("agents/reviewer.md")

        assert "stops being a cold reader" in text


class TestEveryAreaSaysWhatIsNotAFinding:
    """A pedantic acceptance review is worse than none: it is read by the same
    people who agreed the scenarios."""

    def test_the_rubric_carries_a_restraint_clause_per_area(self):
        text = read("references/rubric.md")

        assert text.count("**Not a finding:**") >= 6

    def test_the_dialect_reference_says_where_it_bends(self):
        text = read("references/gherkin.md")

        assert "Where this bends" in text

    def test_an_api_contract_legitimately_names_http(self):
        """The judgement call that separates this lens from a keyword grep: a
        status code is leakage in a user-facing scenario and the agreed
        behaviour when the stakeholder is another service."""
        assert "stakeholder is another service" in read("references/gherkin.md")


class TestProseConsistencyIsNotDryness:
    """The distinction this lens turns on, and the easiest one to collapse.

    The step definitions are code and must be DRY. The scenario text is prose
    and is held to CONSISTENCY — you do not merge two scenarios because they
    read alike, you make them say the same thing the same way. Applying DRY to
    prose would merge away the examples this layer exists to give.
    """

    def test_the_two_standards_are_separate_rubric_areas(self):
        text = read("references/rubric.md")

        assert "the CODE must be DRY" in text
        assert "held to consistency, not to DRY" in text

    def test_the_rubric_says_why_de_duplicating_prose_is_wrong(self):
        assert "examples this layer exists to give" in flat("references/rubric.md")

    def test_it_names_the_cost_to_the_occasional_reader(self):
        """An occasional reader cannot tell deliberate variation from accidental
        variation, so every inconsistency reads as a distinction."""
        assert "cannot tell deliberate variation from accidental" in flat(
            "references/rubric.md"
        )

    @pytest.mark.parametrize(
        "axis",
        [
            "One term per concept",
            "One tense and voice per step keyword",
            "One level of abstraction",
            "One grammar for scenario titles",
            "One name per role",
        ],
    )
    def test_each_consistency_axis_is_named(self, axis):
        assert axis in read("references/rubric.md")

    def test_variation_that_carries_meaning_is_not_a_finding(self):
        """ "the customer" and "the guest" are two actors; flattening them would
        be worse than the inconsistency."""
        rubric = read("references/rubric.md")

        assert "variation that carries meaning" in rubric.lower()
        assert "the guest" in rubric

    def test_house_style_is_not_this_lens_business(self):
        """Consistency is the standard; a particular choice is not."""
        assert "house-style" in read("references/rubric.md")
        assert "does not have opinions about anyone's house style" in flat(
            "references/rubric.md"
        )

    def test_consistency_findings_are_filed_per_concept_not_per_occurrence(self):
        """One finding a human acts on, not thirty-one nobody reads."""
        text = read("references/rubric.md")

        assert "per CONCEPT, not per occurrence" in text

    def test_the_analyzer_builds_the_vocabulary_as_it_reads(self):
        """A concept named three ways is invisible scenario by scenario — the
        same reason the step-definition pass is suite-wide."""
        text = flat("agents/analyzer.md")

        assert "Build the suite's vocabulary as you read" in text
        assert "never once per scenario" in text

    def test_the_analyzer_is_told_not_to_merge_scenarios(self):
        assert "Do not propose merging scenarios to remove repetition" in flat(
            "agents/analyzer.md"
        )

    def test_the_skill_claims_the_dimension_no_other_lens_covers(self):
        text = read("SKILL.md")

        assert "Prose consistency is this lens's alone" in text

    def test_the_umbrella_legend_carries_both_dimensions(self):
        """A consolidated report has to be able to say which of the two a
        finding is."""
        text = (
            REPO_ROOT / "skills/code-quality/references/report-template.md"
        ).read_text()

        assert "definitions · consistency" in text


class TestTheCarveWithAtdd:
    def test_the_build_path_stays_in_atdd(self):
        text = read("SKILL.md")

        assert "atdd" in text
        assert "audit path" in text and "build path" in text

    def test_it_reuses_spec_guardians_rubric_rather_than_reimplementing_it(self):
        assert "spec-guardian" in read("references/rubric.md")

    def test_it_is_report_only_because_a_scenario_is_agreed_behaviour(self):
        """Rewriting a scenario changes what was agreed, which is a
        conversation and not a refactor."""
        text = read("SKILL.md")

        assert "Report-only by default" in text
        assert "conversation, not a refactor" in text


class TestDialectNotLanguage:
    def test_it_varies_by_dialect_where_the_others_vary_by_language(self):
        text = read("SKILL.md")

        assert "Dialect, not language" in text
        assert "<dialect>.md" in read("agents/analyzer.md")

    def test_gherkin_is_loaded_not_hardcoded(self):
        """Gherkin's commercial track record is mixed; hardcoding it would
        inherit that bet, and detecting costs nothing."""
        text = read("SKILL.md")

        assert "deepest-supported" in text
        assert "added as a file" in text


class TestAbsenceIsData:
    def test_no_acceptance_suite_is_an_ordinary_answer(self):
        text = read("SKILL.md")

        assert "ordinary answer" in text
        assert "do not file" in text.lower()

    def test_it_does_not_recommend_adopting_an_acceptance_layer(self):
        """Whether a project should have one is a product decision this lens
        has no standing to make."""
        assert "no standing to make" in read("SKILL.md")

    def test_the_analyzer_stops_rather_than_inventing_scenarios(self):
        text = read("agents/analyzer.md")

        assert "Do not invent scenarios" in text


class TestTheUmbrellaCarriesSevenLenses:
    def test_the_fan_out_table_has_the_seventh_row(self):
        text = UMBRELLA.read_text(encoding="utf-8")

        assert "skills/acceptance-quality/agents/analyzer.md" in text

    def test_it_runs_by_default_and_auto_skips_when_absent(self):
        """Opt-in would mean a repo that HAS acceptance specs silently misses
        the lens; auto-skip means one that does not pays nothing."""
        text = UMBRELLA.read_text(encoding="utf-8")

        assert "auto-skips when Phase 0 finds no suite" in text

    def test_no_stale_six_lens_count_survives(self):
        text = UMBRELLA.read_text(encoding="utf-8").lower()

        assert "six lens" not in text and "six-lens" not in text
        assert "six analyzer" not in text and "six reviewer" not in text

    def test_the_worktree_set_includes_it(self):
        assert "test-quality acceptance-quality" in UMBRELLA.read_text(encoding="utf-8")


class TestTheHubKnowsTheNewOverlaps:
    @pytest.mark.parametrize(
        "overlap", ["ubiquitous language", "near-duplicate step definitions"]
    )
    def test_the_new_rows_are_filed(self, overlap):
        assert overlap in HUB.read_text(encoding="utf-8")

    def test_the_acceptance_vs_unit_boundary_is_stated(self):
        """Both suites covering one behaviour is not duplication — different
        altitudes, different stakeholders."""
        text = HUB.read_text(encoding="utf-8")

        assert "different altitudes, different stakeholders" in text


class TestItHasEvals:
    def test_the_eval_set_exists_and_is_stamped(self):
        document = json.loads(
            (REPO_ROOT / "evals" / "acceptance-quality-evals.json").read_text()
        )

        assert document["reviewed_against_skill_versions"]["acceptance-quality"]
        assert len(document["evals"]) >= 3

    def test_an_eval_covers_the_absent_suite_path(self):
        """The commonest case in the wild, and the one where a lens most easily
        does damage by inventing work."""
        blob = (
            (REPO_ROOT / "evals" / "acceptance-quality-evals.json").read_text().lower()
        )

        assert "no acceptance suite" in blob

    def test_an_eval_covers_the_restraint_call(self):
        blob = (REPO_ROOT / "evals" / "acceptance-quality-evals.json").read_text()

        assert "stakeholder is" in blob
