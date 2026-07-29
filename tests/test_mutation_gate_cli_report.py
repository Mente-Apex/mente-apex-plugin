"""The gate writes its section into the report, not just to stdout.

The lens holds that the report is the single source of truth. A gate whose
survivors only ever reach stdout breaks that: the operator reads the report,
the report says `_Not yet run._`, and a real finding is invisible. These tests
pin the marker contract itself, so the splice cannot rot back into prose.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import mutation_gate
import mutation_gate_backends
from mutation_gate import GateResult, Survivor
from mutation_gate_report import (
    BEGIN_MARKER,
    END_MARKER,
    render_markdown,
    splice_into_report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def report_with_markers(body="_Not yet run._"):
    return (
        "# Test-quality Audit\n\n"
        "## Mutation gate\n\n"
        f"{BEGIN_MARKER}\n{body}\n{END_MARKER}\n\n"
        "## Apply log\n"
    )


class TestSplicingIntoTheReport:
    def test_the_section_lands_between_the_markers(self):
        spliced = splice_into_report(report_with_markers(), "**Scope:** merge-base")

        assert "_Not yet run._" not in spliced
        body = spliced.split(BEGIN_MARKER)[1].split(END_MARKER)[0]
        assert body.strip() == "**Scope:** merge-base"

    def test_everything_outside_the_markers_is_left_byte_identical(self):
        original = report_with_markers()

        spliced = splice_into_report(original, "anything at all")

        assert spliced.startswith(original.split(BEGIN_MARKER)[0])
        assert spliced.endswith(original.split(END_MARKER)[1])

    def test_splicing_twice_replaces_rather_than_accumulates(self):
        once = splice_into_report(report_with_markers(), "first run")

        twice = splice_into_report(once, "second run")

        assert "first run" not in twice
        assert twice.count(BEGIN_MARKER) == 1

    def test_a_report_with_no_markers_raises_rather_than_dropping_the_section(self):
        with pytest.raises(ValueError, match="mutation-gate:begin"):
            splice_into_report("# Report\n\nNo markers here.\n", "survivors")

    def test_markers_in_the_wrong_order_raise(self):
        text = f"{END_MARKER}\n{BEGIN_MARKER}\n"

        with pytest.raises(ValueError, match="order"):
            splice_into_report(text, "survivors")

    def test_duplicate_markers_raise_rather_than_guessing_which_pair(self):
        text = report_with_markers() + report_with_markers()

        with pytest.raises(ValueError, match="more than once"):
            splice_into_report(text, "survivors")


class TestTheCliWritesTheReport:
    @pytest.fixture
    def gate_without_a_real_run(self, monkeypatch):
        """Everything expensive stubbed; only the report wiring is under test."""
        survivor = Survivor(
            artifact="src/money.py",
            location="money.discount",
            mutant="and -> or",
            associated_tests=("tests/test_money.py::test_discount",),
            backend="mutmut",
            granularity="function",
        )
        monkeypatch.setattr(
            mutation_gate, "changed_paths", lambda root, scope: ("src/money.py",)
        )
        monkeypatch.setattr(
            mutation_gate, "_record_baseline", lambda root, run: ((), "")
        )
        monkeypatch.setattr(mutation_gate_backends, "default_backends", tuple)
        monkeypatch.setattr(
            mutation_gate,
            "run_gate",
            lambda *a, **k: GateResult(
                survivors=(survivor,),
                unavailable=(),
                unresolved=(),
                unclaimed=(),
            ),
        )

    def test_the_survivor_reaches_the_report_file_not_only_stdout(
        self, gate_without_a_real_run, tmp_path, capsys
    ):
        report = tmp_path / "TEST-QUALITY-REPORT.md"
        report.write_text(report_with_markers(), encoding="utf-8")

        exit_code = mutation_gate.main(
            ["--repo-root", str(tmp_path), "--report", str(report)]
        )

        assert exit_code == 0
        written = report.read_text(encoding="utf-8")
        assert "money.discount" in written
        assert "_Not yet run._" not in written

    def test_the_json_still_goes_to_stdout_for_the_analyzer(
        self, gate_without_a_real_run, tmp_path, capsys
    ):
        report = tmp_path / "report.md"
        report.write_text(report_with_markers(), encoding="utf-8")

        mutation_gate.main(["--repo-root", str(tmp_path), "--report", str(report)])

        payload = json.loads(capsys.readouterr().out)
        assert payload["survivors"][0]["location"] == "money.discount"

    def test_a_report_path_that_does_not_exist_fails_loudly(
        self, gate_without_a_real_run, tmp_path, capsys
    ):
        with pytest.raises(FileNotFoundError):
            mutation_gate.main(
                ["--repo-root", str(tmp_path), "--report", str(tmp_path / "nope.md")]
            )

        # The JSON was still emitted before the failure -- the analyzer's copy of
        # the result is not lost to a report-writing problem.
        assert json.loads(capsys.readouterr().out)["survivors"]

    def test_no_report_flag_writes_no_file_and_still_prints_json(
        self, gate_without_a_real_run, tmp_path, capsys
    ):
        before = sorted(p.name for p in tmp_path.iterdir())

        mutation_gate.main(["--repo-root", str(tmp_path)])

        assert sorted(p.name for p in tmp_path.iterdir()) == before
        assert json.loads(capsys.readouterr().out)["scope"] == "merge-base"


class TestTheTemplateClaimIsTrue:
    def test_the_shipped_template_carries_the_markers_the_cli_writes_between(self):
        template = (
            REPO_ROOT / "skills/test-quality/references/report-template.md"
        ).read_text(encoding="utf-8")

        assert BEGIN_MARKER in template
        assert END_MARKER in template

    def test_the_cli_can_actually_fill_the_shipped_template(self):
        template_path = REPO_ROOT / "skills/test-quality/references/report-template.md"
        template = template_path.read_text(encoding="utf-8")
        section = render_markdown(
            GateResult(
                survivors=(),
                unavailable=(),
                unresolved=(),
                unclaimed=(),
            ),
            scope="merge-base",
        )

        spliced = splice_into_report(template, section)

        filled = spliced.split(BEGIN_MARKER)[1].split(END_MARKER)[0]
        assert "**Scope:** merge-base" in filled
        assert "_Not yet run._" not in filled
        assert "%" not in filled

    def test_the_cli_exposes_the_report_flag_the_template_claims(self):
        help_text = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/mutation_gate.py"), "--help"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        assert "--report" in help_text
