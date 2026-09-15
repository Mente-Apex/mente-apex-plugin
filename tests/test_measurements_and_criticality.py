"""The consolidated report gets numbers, and the gate gets an attention weight.

Three issues, one surface:

- **#118** — the report had no place for a number. Every section was
  qualitative, and `## Outcome` proved an apply run with "suite: 1381 → 1388
  passed, green", which proves nothing broke and says nothing about whether the
  refactor DID anything.
- **#119** — the mutation machinery was diff-scoped at both call sites, so the
  score it could produce was never asked for. `--scope full` already existed;
  this was a call-site gap.
- **#120** — audit depth was uniform. The apply side already scales by Risk
  (Low→haiku, Med→sonnet, High→opus); the audit side treated a formatting helper
  and a payments module identically.

The shared rule across all three is the one the Coverage section already
carries: **absence is data, never silence.** A sensor that could not run omits
its row and says why; it never prints a reassuring number.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "skills" / "code-quality" / "references" / "report-template.md"
UMBRELLA = REPO_ROOT / "skills" / "code-quality" / "SKILL.md"


def template():
    return TEMPLATE.read_text(encoding="utf-8")


def umbrella():
    return UMBRELLA.read_text(encoding="utf-8")


class TestTheMeasurementsSection:
    def test_the_report_has_one_at_all(self):
        assert "## Measurements" in template()

    def test_it_sits_between_summary_and_the_findings_index(self):
        """It is the dashboard a reader scans BEFORE any finding. Below the
        index it is an appendix nobody reaches.

        Ordering is read from the `## Shape` block — the template's own
        rendering of the report — because the sections are also described
        individually further up, in a different order."""
        shape = template().split("## Shape", 1)[1]

        assert shape.index("## Summary") < shape.index("## Measurements")
        assert shape.index("## Measurements") < shape.index("## Findings index")

    @pytest.mark.parametrize(
        "sensor",
        [
            "Cyclomatic complexity",
            "Module size",
            "Import cycles",
            "Coverage",
            "Mutation score",
        ],
    )
    def test_it_carries_each_sensor(self, sensor):
        assert sensor in template()

    def test_complexity_and_size_are_distributions_not_averages(self):
        """A mean hides the one 1889-line module that is the finding."""
        text = template()

        assert "p95" in text and "max" in text

    def test_the_worst_offender_is_located_not_just_counted(self):
        """ "max 31" is a number; "max 31 (`orders.py:214`)" is actionable."""
        assert "file:line" in template()

    def test_an_unmeasurable_sensor_omits_its_row_rather_than_faking_one(self):
        text = template()

        assert "never fake a row" in text
        assert "absence is data, never silence" in text


class TestTheBeforeAfterDelta:
    def test_the_outcome_section_carries_a_measured_effect_line(self):
        assert "**Measured effect:**" in template()

    def test_it_shows_movement_not_an_endpoint(self):
        """The point is the arrow: "CC p95 12" says nothing without the 31 it
        came from."""
        text = template()

        assert "→" in text.split("**Measured effect:**")[1][:400]

    def test_a_sensor_measured_only_once_is_omitted_from_the_delta(self):
        """A delta with a guessed endpoint is worse than no delta."""
        assert "guessed endpoint" in template()

    def test_it_is_omitted_on_an_audit_only_run(self):
        """Same rule the Outcome section already follows — there is no "after"
        when nothing was applied."""
        delta_note = template().split("**Measured effect:**")[1][:600]

        assert "audit-only run" in delta_note


class TestTheMutationSensorIsOptIn:
    def test_the_umbrella_names_the_flag(self):
        assert "`--mutation`" in umbrella()

    def test_it_is_off_by_default_and_says_why(self):
        text = umbrella()

        assert "Off by default" in text
        assert "expensive" in text

    def test_it_runs_the_full_scope_the_gate_already_supports(self):
        """#119's point: this was a call-site gap, not a missing capability."""
        assert "--scope full" in umbrella()

    def test_the_survivors_are_not_replaced_by_the_score(self):
        """A score with the survivors swallowed is the "87%" the issue
        explicitly did not want."""
        text = umbrella()

        assert "still\nenumerated" in text or "still enumerated" in text


class TestTheCriticalityHintIsAnAttentionWeight:
    def test_the_umbrella_takes_an_explicit_flag(self):
        assert "`--critical <path>…`" in umbrella()

    def test_it_is_never_inferred_from_path_names(self):
        """#120 names inference as the risky part: guessing that `payments/` is
        critical and `billing_helpers/` is not is a confident wrong answer."""
        text = umbrella()

        assert "never\ninferred" in text or "never inferred" in text

    def test_it_does_not_become_a_second_severity_axis(self):
        """The caveat the issue is most emphatic about: this is presentation,
        and Critical/Major/Minor keep meaning what they meant."""
        text = umbrella()

        assert "attention weight on presentation, not a second severity axis" in text
        assert "Tiers stay Critical/Major/Minor" in text

    def test_the_phase_3_gate_leads_with_critical_subtrees(self):
        text = umbrella()

        assert "lead\nwith the findings that sit in those subtrees" in text or (
            "lead with the findings that sit in those subtrees" in text
        )

    def test_not_declared_is_an_ordinary_answer(self):
        """Most repos will not declare one, and the audit must not nag."""
        assert "Not declared is an ordinary answer" in umbrella()

    def test_the_report_records_what_was_declared(self):
        assert "Criticality:" in template()
