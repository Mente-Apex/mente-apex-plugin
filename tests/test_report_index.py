"""The consolidated report has to be true about itself.

Three complaints, one root cause: the Findings index is a dashboard, and it was
prose nothing verified. So the apply order was a column rather than a queue
anything consumed, a `Status:` line and its index row were two places to write
one fact with nothing comparing them, and a reader misled once by a stale status
stops trusting the table and goes back to the wall of prose the index exists to
replace.

These tests are mostly about the two failures that are expensive: an order
jumped without a reason, and work that happened but was never stamped.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from report_index import (
    STATUS_PATTERNS,
    Violation,
    check_report,
    parse_report,
    progress_line,
    the_apply_order_is_a_queue,
)


def report(rows, findings, apply_log=""):
    """A consolidated report with the three sections the checker reads."""
    index = "\n".join(
        f"| {order} | `{finding_id}` {title} | SOLID · SRP | Low | {status} |"
        for order, finding_id, title, status in rows
    )
    bodies = "\n".join(
        f"#### [{finding_id}] {title}\n\n- **Status:** {status}\n"
        for finding_id, title, status in findings
    )
    return f"""# Code Quality — demo — 2026-09-15

## Summary

Two findings.

## Findings index

| # | Finding | Breaks | Risk | Status |
|---|---|---|---|---|
{index}

## Findings

{bodies}

## Apply log

{apply_log}
"""


def rule_names(violations):
    return sorted(violation.rule for violation in violations)


class TestStampingIsChecked:
    """ "The issues are not stamped accordingly" — the same fact written twice."""

    def test_a_clean_report_has_no_violations(self):
        text = report(
            rows=[(1, "solid/major-1", "Split the god-module", "pending")],
            findings=[("solid/major-1", "Split the god-module", "pending")],
        )

        assert check_report(text) == []

    def test_an_index_row_disagreeing_with_its_finding_is_caught(self):
        """A stale dashboard is worse than none: it is read, believed, wrong."""
        text = report(
            rows=[(1, "solid/major-1", "Split the god-module", "applied")],
            findings=[("solid/major-1", "Split the god-module", "pending")],
        )

        assert "status-drift" in rule_names(check_report(text))

    def test_work_recorded_in_the_log_but_never_stamped_is_caught(self):
        """The commonest miss: the edit landed, the log says so, and the Status
        line was never moved."""
        text = report(
            rows=[(1, "solid/major-1", "Split", "pending")],
            findings=[("solid/major-1", "Split", "pending")],
            apply_log="2026-09-15T10:00Z [solid/major-1] applied — covered — green",
        )

        assert "stale-pending" in rule_names(check_report(text))

    def test_an_applied_finding_with_no_log_line_is_caught(self):
        """The claim without the evidence. That safety clause is what makes "a
        safe refactor actually ran" observable rather than taken on faith."""
        text = report(
            rows=[(1, "solid/major-1", "Split", "applied")],
            findings=[("solid/major-1", "Split", "applied")],
            apply_log="2026-09-15T10:00Z [gof/minor-9] applied — covered — green",
        )

        assert "unlogged-apply" in rule_names(check_report(text))

    def test_an_invented_status_is_caught(self):
        """ "in progress" reads fine and means nothing to the Outcome synthesis
        that has to count them."""
        text = report(
            rows=[(1, "solid/major-1", "Split", "in progress")],
            findings=[("solid/major-1", "Split", "in progress")],
        )

        assert "unknown-status" in rule_names(check_report(text))

    def test_a_finding_with_no_status_line_at_all_is_caught(self):
        text = """# R

## Findings index

| # | Finding | Breaks | Risk | Status |
|---|---|---|---|---|
| 1 | `solid/major-1` Split | SOLID · SRP | Low | pending |

## Findings

#### [solid/major-1] Split

- **Location:** `a.py:1`
"""

        assert "missing-status" in rule_names(check_report(text))

    @pytest.mark.parametrize(
        "status",
        [
            "pending",
            "applied",
            "applied (via solid/major-1)",
            "failed (reverted)",
            "skipped (not approved)",
            "skipped (lost conflict to gof/major-2)",
        ],
    )
    def test_every_canonical_status_is_accepted(self, status):
        """The vocabulary is defined in docs/refactor-workflow.md; this rule must
        not quietly narrow it — two of the values carry a payload."""
        text = report(
            rows=[(1, "solid/major-1", "Split", status)],
            findings=[("solid/major-1", "Split", status)],
        )

        assert "unknown-status" not in rule_names(check_report(text))


class TestTheApplyOrderIsAQueue:
    """ "The apply order is not always followed" — it was a column, not a queue."""

    def test_applying_in_order_is_clean(self):
        text = report(
            rows=[
                (1, "solid/major-1", "First", "applied"),
                (2, "gof/major-1", "Second", "pending"),
            ],
            findings=[
                ("solid/major-1", "First", "applied"),
                ("gof/major-1", "Second", "pending"),
            ],
            apply_log="2026-09-15T10:00Z [solid/major-1] applied — covered — green",
        )

        assert "order-jumped" not in rule_names(check_report(text))

    def test_jumping_the_queue_is_caught(self):
        """The expensive failure this hides: a change applied before the change
        that was supposed to give it a home."""
        text = report(
            rows=[
                (1, "solid/major-1", "Split the module", "pending"),
                (2, "clean-code/minor-1", "Extract the helper", "applied"),
            ],
            findings=[
                ("solid/major-1", "Split the module", "pending"),
                ("clean-code/minor-1", "Extract the helper", "applied"),
            ],
            apply_log="2026-09-15T10:00Z [clean-code/minor-1] applied — covered — green",
        )

        violations = check_report(text)

        assert "order-jumped" in rule_names(violations)
        jumped = next(
            violation for violation in violations if violation.rule == "order-jumped"
        )
        assert jumped.finding_id == "clean-code/minor-1"

    def test_the_violation_names_the_remedy_not_just_the_problem(self):
        """Reordering deliberately is allowed — it just has to be visible."""
        text = report(
            rows=[
                (1, "solid/major-1", "First", "pending"),
                (2, "gof/minor-1", "Second", "applied"),
            ],
            findings=[
                ("solid/major-1", "First", "pending"),
                ("gof/minor-1", "Second", "applied"),
            ],
            apply_log="2026-09-15T10:00Z [gof/minor-1] applied — covered — green",
        )

        jumped = next(
            violation
            for violation in check_report(text)
            if violation.rule == "order-jumped"
        )

        # Both remedies, and both reachable: restamp the blocker, or note the
        # deliberate reorder where the rule can see it.
        assert "skipped (not approved)" in jumped.detail
        assert "out of turn" in jumped.detail

    def test_a_skipped_finding_does_not_block_the_ones_after_it(self):
        """Skipped is resolved. Treating it as a blocker would stall the queue on
        every finding the human declined."""
        text = report(
            rows=[
                (1, "solid/major-1", "First", "skipped (not approved)"),
                (2, "gof/major-1", "Second", "applied"),
            ],
            findings=[
                ("solid/major-1", "First", "skipped (not approved)"),
                ("gof/major-1", "Second", "applied"),
            ],
            apply_log="2026-09-15T10:00Z [gof/major-1] applied — covered — green",
        )

        assert "order-jumped" not in rule_names(check_report(text))

    def test_an_audit_only_report_is_clean(self):
        """Nothing applied, nothing out of order — the ordinary case, and it must
        not produce noise."""
        text = report(
            rows=[
                (1, "solid/major-1", "First", "pending"),
                (2, "gof/major-1", "Second", "pending"),
            ],
            findings=[
                ("solid/major-1", "First", "pending"),
                ("gof/major-1", "Second", "pending"),
            ],
        )

        assert check_report(text) == []


class TestIndexAndBodyAgree:
    def test_a_finding_missing_from_the_index_is_caught(self):
        """Invisible to the reader who is using the table instead of the prose,
        which is every reader the index was added for."""
        text = report(
            rows=[(1, "solid/major-1", "First", "pending")],
            findings=[
                ("solid/major-1", "First", "pending"),
                ("gof/minor-1", "Unindexed", "pending"),
            ],
        )

        assert "unindexed-finding" in rule_names(check_report(text))

    def test_a_row_pointing_at_nothing_is_caught(self):
        text = report(
            rows=[
                (1, "solid/major-1", "First", "pending"),
                (2, "gof/minor-9", "Ghost", "pending"),
            ],
            findings=[("solid/major-1", "First", "pending")],
        )

        assert "dangling-index-row" in rule_names(check_report(text))

    def test_a_report_with_no_index_at_all_says_so_first(self):
        assert check_report("# R\n\n## Summary\n\nNothing.\n")[0].rule == "no-index"


class TestTheProgressLine:
    def test_it_states_where_the_run_stands(self):
        text = report(
            rows=[
                (1, "solid/major-1", "First", "applied"),
                (2, "gof/major-1", "Second", "pending"),
                (3, "ddd/minor-1", "Third", "skipped (not approved)"),
            ],
            findings=[
                ("solid/major-1", "First", "applied"),
                ("gof/major-1", "Second", "pending"),
                ("ddd/minor-1", "Third", "skipped (not approved)"),
            ],
            apply_log="2026-09-15T10:00Z [solid/major-1] applied — covered — green",
        )

        assert (
            progress_line(parse_report(text))
            == "1 of 3 applied · 1 pending · 1 skipped"
        )

    def test_it_omits_the_buckets_that_are_empty(self):
        text = report(
            rows=[(1, "solid/major-1", "First", "pending")],
            findings=[("solid/major-1", "First", "pending")],
        )

        assert progress_line(parse_report(text)) == "0 of 1 applied · 1 pending"


class TestRulesAreData:
    def test_a_caller_can_run_one_rule_alone(self):
        """The OCP seam: rules are functions in a list, so a new check is a new
        function and a narrower run is a shorter list."""
        text = report(
            rows=[(1, "solid/major-1", "First", "nonsense")],
            findings=[("solid/major-1", "First", "nonsense")],
        )

        assert check_report(text, rules=(the_apply_order_is_a_queue,)) == []

    def test_a_violation_reads_as_one_line(self):
        violation = Violation("order-jumped", "applied out of turn", "solid/major-1")

        assert str(violation) == "order-jumped [solid/major-1]: applied out of turn"


class TestTheCli:
    @staticmethod
    def run_cli(*arguments):
        return subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[1] / "scripts" / "report_index.py"
                ),
                *arguments,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_it_prints_the_progress_line_and_the_verdict(self, tmp_path):
        path = tmp_path / "CODE-QUALITY-REPORT-2026-09-15.md"
        path.write_text(
            report(
                rows=[(1, "solid/major-1", "First", "pending")],
                findings=[("solid/major-1", "First", "pending")],
            ),
            encoding="utf-8",
        )

        completed = self.run_cli(str(path))

        assert completed.returncode == 0
        assert "0 of 1 applied" in completed.stdout
        assert "✓" in completed.stdout

    def test_it_is_advisory_by_default(self, tmp_path):
        """A report mid-apply is legitimately inconsistent for as long as one
        edit takes, so the plain run reports and exits 0."""
        path = tmp_path / "r.md"
        path.write_text(
            report(
                rows=[(1, "solid/major-1", "First", "applied")],
                findings=[("solid/major-1", "First", "pending")],
            ),
            encoding="utf-8",
        )

        completed = self.run_cli(str(path))

        assert completed.returncode == 0
        assert "status-drift" in completed.stdout

    def test_strict_blocks_for_a_hook_or_ci(self, tmp_path):
        path = tmp_path / "r.md"
        path.write_text(
            report(
                rows=[(1, "solid/major-1", "First", "applied")],
                findings=[("solid/major-1", "First", "pending")],
            ),
            encoding="utf-8",
        )

        assert self.run_cli(str(path), "--strict").returncode == 1

    def test_a_missing_report_is_an_error_not_a_traceback(self, tmp_path):
        completed = self.run_cli(str(tmp_path / "nope.md"))

        assert completed.returncode == 2
        assert "Traceback" not in completed.stderr


class TestTheTemplateIsTrueToItsOwnChecker:
    """The example in the template is what an agent copies. If it does not pass
    the checker the template points at, every report starts life failing."""

    @staticmethod
    def shape_block():
        """The template's own rendering of a report, from the `## Shape` section.

        Read from the fenced block so the surrounding SPEC prose — which
        describes sections in a different order and quotes headings — is not
        parsed as if it were a report.
        """
        template = (
            Path(__file__).resolve().parents[1]
            / "skills/code-quality/references/report-template.md"
        ).read_text(encoding="utf-8")
        shape = template.split("## Shape", 1)[1]
        return shape.split("```markdown", 1)[1].rsplit("```", 1)[0]

    def test_the_example_index_parses(self):
        parsed = parse_report(self.shape_block())

        assert parsed.has_index
        assert len(parsed.index_rows) >= 4

    def test_the_example_opens_with_a_progress_line(self):
        """The state before the first row, so a reader knows where the run
        stands without counting."""
        assert "applied ·" in self.shape_block()

    def test_the_example_table_has_five_columns(self):
        """Eight wrapped on any realistic width and squeezed the title — the one
        column a reader actually scans."""
        header = next(
            line
            for line in self.shape_block().splitlines()
            if line.strip().startswith("| #")
        )

        assert len(header.strip().strip("|").split("|")) == 5

    def test_the_example_marks_grouped_members_on_the_order_number(self):
        """A grouped change is one job, so its members share the number — the
        role marker rides along rather than taking a column of its own."""
        block = self.shape_block()

        assert "2ᴾ" in block and "2ᴿ" in block

    def test_the_example_passes_the_checker_completely(self):
        """The assertion this class's docstring always claimed to make.

        It checked one rule — `group-split` — while the example failed five
        others: an index listing four findings the body did not contain, elided
        stubs with no Status line, and Apply-log examples naming IDs that existed
        nowhere. An agent copying the shape inherited a report that fails at the
        Phase 3 gate and blocks Phase 5 `--strict` on template scaffolding.
        """
        assert check_report(self.shape_block()) == []

    def test_a_commented_apply_log_example_is_not_read_as_an_entry(self):
        """Every lens template shows the log format as commented examples.
        Reading one as real work reported the template's own scaffolding as
        something somebody forgot to stamp."""
        commented = report(
            rows=[(1, "solid/major-1", "Thing", "pending")],
            findings=[("solid/major-1", "Thing", "pending")],
            apply_log="<!-- <UTC ts> [solid/major-1] applied — covered — green -->",
        )

        assert "stale-pending" not in rule_names(check_report(commented))

    def test_the_template_points_at_the_checker(self):
        template = (
            Path(__file__).resolve().parents[1]
            / "skills/code-quality/references/report-template.md"
        ).read_text(encoding="utf-8")

        assert "report_index.py" in template
        assert "--strict" in template


class TestThePhasesRunTheChecker:
    """Prose asking an agent to keep three views in sync is a guard nothing can
    check. These pin that the check is actually invoked, at both points where a
    stale index does damage."""

    @staticmethod
    def umbrella():
        return (
            Path(__file__).resolve().parents[1] / "skills/code-quality/SKILL.md"
        ).read_text(encoding="utf-8")

    def test_the_phase_3_gate_checks_before_the_human_reads_it(self):
        """A gate presented from a stale index asks the human to decide using
        numbers that are wrong."""
        text = self.umbrella()
        gate = text.split("### Phase 3", 1)[1][:1200]

        assert "report_index.py" in gate

    def test_phase_5_checks_strictly_before_writing_the_outcome(self):
        """The Outcome is a synthesis of statuses, so it inherits every
        disagreement the index still carries."""
        text = self.umbrella()

        assert "report_index.py --strict" in text


class TestTheVocabularyIsNotTranscribed:
    """`deferred` got into this module because the vocabulary was retyped here
    instead of being read from the document that defines it. The result was a
    status the checker accepted, the template advertised, and the canonical
    document had never heard of — which made the queue rule incoherent, since a
    `deferred` row was neither resolved nor pending."""

    @staticmethod
    def declared_in_the_doc():
        """The statuses docs/refactor-workflow.md actually defines."""
        workflow = (
            Path(__file__).resolve().parents[1] / "docs/refactor-workflow.md"
        ).read_text(encoding="utf-8")
        bullet = workflow.split("**Status values**", 1)[1].split("- **Apply-log", 1)[0]
        return set(re.findall(r"`([a-z]+(?: \([^`]+\))?)`", bullet))

    def test_the_doc_still_declares_a_vocabulary_this_test_can_read(self):
        """Guard on the guard: if the bullet is reworded past recognition, the
        comparison below would compare two empty sets and pass forever."""
        declared = self.declared_in_the_doc()

        assert "pending" in declared and "applied" in declared

    def test_the_module_accepts_nothing_the_doc_does_not_define(self):
        for status in self.declared_in_the_doc():
            spelled = status.replace("<winner-id>", "gof/major-2")
            assert any(
                re.match(pattern, spelled) for pattern in STATUS_PATTERNS
            ), f"the doc defines {status!r} and this module rejects it"

    def test_deferred_is_rejected_because_the_doc_never_defined_it(self):
        assert "deferred" not in self.declared_in_the_doc()
        assert not any(re.match(pattern, "deferred") for pattern in STATUS_PATTERNS)


class TestTheProgressLineDoesNotFlatterTheRun:
    def test_reverted_work_is_never_counted_as_applied(self):
        """Three attempts, all reverted, used to read "3 of 3 applied" — to the
        reader at the gate and to the Outcome synthesis built from the same
        statuses."""
        text = report(
            rows=[
                (index, f"solid/major-{index}", "Tried", "failed (reverted)")
                for index in (1, 2, 3)
            ],
            findings=[
                (f"solid/major-{index}", "Tried", "failed (reverted)")
                for index in (1, 2, 3)
            ],
        )

        assert progress_line(parse_report(text)) == "0 of 3 applied · 3 reverted"

    def test_an_unreadable_status_is_not_silently_called_pending(self):
        """ "we cannot read this row" and "this row is queued" are different
        facts, and only one of them is the reader's problem."""
        text = report(
            rows=[(1, "solid/major-1", "Odd", "in progress")],
            findings=[("solid/major-1", "Odd", "in progress")],
        )

        assert "1 unstamped" in progress_line(parse_report(text))
