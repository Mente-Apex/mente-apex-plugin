"""The parser is tested against captured CSV; the probe is tested against a
stub runner. One real-lizard test runs over the committed Java 25 fixtures —
that one is the regression net for "can we still parse this language".
"""

from pathlib import Path

from complexity_probe_lizard import LizardProbe, LizardRunFailedError, parse_lizard_csv
from complexity_probe_measurement import RAN, UNVERIFIED

FIXTURES = Path(__file__).resolve().parents[1] / "tests/fixtures/probe/java"

CAPTURED_CSV = (
    '9,6,114,1,9,"AreaCalculator::area@9-17@/x/Shape.java","/x/Shape.java",'
    '"AreaCalculator::area","AreaCalculator::area( Shape shape)",9,17\n'
    '11,7,93,0,11,"main@3-13@/x/Compact.java","/x/Compact.java",'
    '"main","main()",3,13\n'
)


class TestParsingLizardCsv:
    def test_every_row_becomes_a_metric(self):
        metrics = parse_lizard_csv(CAPTURED_CSV)
        assert len(metrics) == 2

    def test_columns_land_in_the_right_fields(self):
        first_metric = parse_lizard_csv(CAPTURED_CSV)[0]
        assert first_metric.name == "AreaCalculator::area"
        assert first_metric.path == "/x/Shape.java"
        assert first_metric.cyclomatic_complexity == 6
        assert first_metric.length == 9
        assert first_metric.parameter_count == 1
        assert first_metric.start_line == 9
        assert first_metric.end_line == 17

    def test_empty_output_is_no_metrics_not_an_error(self):
        assert parse_lizard_csv("") == ()

    def test_a_malformed_row_is_skipped_rather_than_crashing(self):
        metrics = parse_lizard_csv("not,enough,columns\n" + CAPTURED_CSV)
        assert len(metrics) == 2


class StubRunner:
    """Stands in for subprocess so probe behavior is testable without lizard."""

    def __init__(self, stdout="", available=True, raises=None):
        self.stdout = stdout
        self.available = available
        self.raises = raises
        self.calls = []

    def is_available(self):
        return self.available

    def run(self, paths):
        self.calls.append(tuple(paths))
        if self.raises:
            raise self.raises
        return self.stdout


class TestTheProbe:
    def test_a_successful_run_is_ran(self):
        probe = LizardProbe(runner=StubRunner(stdout=CAPTURED_CSV))
        measurement = probe.measure(["/x/Shape.java"])
        assert measurement.status == RAN
        assert len(measurement.functions) == 2

    def test_an_unavailable_tool_is_unverified_with_a_reason(self):
        probe = LizardProbe(runner=StubRunner(available=False))
        measurement = probe.measure(["/x/Shape.java"])
        assert measurement.status == UNVERIFIED
        assert "lizard" in measurement.reason

    def test_a_crashing_run_is_unverified_not_an_exception(self):
        probe = LizardProbe(runner=StubRunner(raises=OSError("boom")))
        measurement = probe.measure(["/x/Shape.java"])
        assert measurement.status == UNVERIFIED
        assert "boom" in measurement.reason

    def test_a_failed_run_with_stderr_is_unverified_with_reason(self):
        """Non-zero exit with stderr triggers LizardRunFailedError, caught as UNVERIFIED."""
        probe = LizardProbe(
            runner=StubRunner(
                raises=LizardRunFailedError(
                    "Error: Fail to read source file '/x/bad.java'"
                )
            )
        )
        measurement = probe.measure(["/x/bad.java"])
        assert measurement.status == UNVERIFIED
        assert "Fail to read source file" in measurement.reason

    def test_a_failed_run_with_exit_code_is_unverified_with_reason(self):
        """Non-zero exit without stderr triggers LizardRunFailedError with exit code."""
        probe = LizardProbe(runner=StubRunner(raises=LizardRunFailedError("exit 2")))
        measurement = probe.measure(["/x/Shape.java"])
        assert measurement.status == UNVERIFIED
        assert "exit 2" in measurement.reason

    def test_no_paths_is_ran_with_no_functions(self):
        """An empty change set measured is an answer, not a gap."""
        runner = StubRunner()
        measurement = LizardProbe(runner=runner).measure([])
        assert measurement.status == RAN
        assert measurement.functions == ()
        assert runner.calls == []


class TestAgainstRealLizardOnJava25:
    """Regression net for the committed fixtures. Baseline recorded in
    tests/fixtures/probe/java/README.md."""

    def test_java_25_fixtures_parse_with_the_recorded_baseline(self):
        probe = LizardProbe()
        if not probe.is_available():
            import pytest

            pytest.skip("lizard not installed")
        measurement = probe.measure([str(FIXTURES)])
        assert measurement.status == RAN
        by_name = {metric.name: metric for metric in measurement.functions}
        assert by_name["AreaCalculator::area"].cyclomatic_complexity == 6
        assert by_name["main"].cyclomatic_complexity == 7
        assert by_name["Account::Account"].cyclomatic_complexity == 4
