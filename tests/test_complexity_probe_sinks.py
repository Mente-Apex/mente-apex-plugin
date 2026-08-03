"""One measurement, three renderings. No sink may word a breach as a failure —
numbers point, they do not judge."""

import json

from complexity_probe_measurement import (
    DEGRADED,
    RAN,
    UNVERIFIED,
    FunctionMetric,
    Measurement,
)
from complexity_probe_sinks import ArtifactSink, ReviewSink, TranscriptSink
from complexity_probe_thresholds import (
    NO_THRESHOLDS,
    Thresholds,
    no_thresholds_because,
)


def measurement_with(cyclomatic_complexity):
    return Measurement(
        status=RAN,
        functions=(
            FunctionMetric(
                name="OrderService::applyDiscount",
                path="src/OrderService.java",
                start_line=40,
                end_line=78,
                cyclomatic_complexity=cyclomatic_complexity,
                length=38,
                parameter_count=2,
            ),
        ),
    )


class TestTheTranscriptSink:
    def test_it_names_every_function_with_its_numbers(self):
        rendered = TranscriptSink().render(measurement_with(14), NO_THRESHOLDS)
        assert "OrderService::applyDiscount" in rendered
        assert "14" in rendered

    def test_an_unverified_measurement_renders_its_reason(self):
        rendered = TranscriptSink().render(
            Measurement(status=UNVERIFIED, reason="needs compiled classes"),
            NO_THRESHOLDS,
        )
        assert "unverified" in rendered
        assert "needs compiled classes" in rendered

    def test_a_measurement_with_no_functions_says_so_explicitly(self):
        rendered = TranscriptSink().render(Measurement(status=RAN), NO_THRESHOLDS)
        assert rendered.strip()
        assert "no functions" in rendered.lower()

    def test_a_degraded_measurement_shows_functions_and_the_reason(self):
        degraded = Measurement(
            status=DEGRADED,
            functions=(
                FunctionMetric(
                    name="incomplete::analyze",
                    path="src/Parser.java",
                    start_line=20,
                    end_line=45,
                    cyclomatic_complexity=8,
                    length=25,
                    parameter_count=1,
                ),
            ),
            reason="missing nested class definitions",
            skipped=("src/Nested.java",),
        )
        rendered = TranscriptSink().render(degraded, NO_THRESHOLDS)
        assert "incomplete::analyze" in rendered
        assert "8" in rendered
        assert "degraded" in rendered
        assert "missing nested class definitions" in rendered
        assert "src/Nested.java" in rendered


class TestBreachesPointRatherThanJudge:
    def test_a_breach_is_marked_as_a_place_to_look(self):
        thresholds = Thresholds(cyclomatic_complexity=10, source="checkstyle.xml")
        rendered = TranscriptSink().render(measurement_with(14), thresholds)
        assert "look" in rendered.lower()

    def test_no_sink_calls_a_breach_a_failure(self):
        thresholds = Thresholds(cyclomatic_complexity=10, source="checkstyle.xml")
        for sink in (TranscriptSink(), ReviewSink()):
            rendered = sink.render(measurement_with(14), thresholds)
            lowered = rendered.lower()
            for forbidden_word in ("fail", "violation", "error", "must fix"):
                assert forbidden_word not in lowered

    def test_without_a_threshold_nothing_is_flagged(self):
        rendered = TranscriptSink().render(measurement_with(99), NO_THRESHOLDS)
        assert "look" not in rendered.lower()

    def test_a_degraded_measurement_with_no_functions_preserves_the_reason(self):
        degraded_empty = Measurement(
            status=DEGRADED,
            functions=(),
            reason="incomplete parse due to missing imports",
            skipped=("src/Missing.java", "src/External.java"),
        )
        rendered = TranscriptSink().render(degraded_empty, NO_THRESHOLDS)
        assert "degraded" in rendered
        assert "incomplete parse due to missing imports" in rendered
        assert "src/Missing.java" in rendered
        assert "src/External.java" in rendered

    def test_no_sink_guards_against_breach_words_in_degraded_rendering(self):
        degraded_with_functions = Measurement(
            status=DEGRADED,
            functions=(
                FunctionMetric(
                    name="partial::process",
                    path="src/Handler.java",
                    start_line=10,
                    end_line=30,
                    cyclomatic_complexity=12,
                    length=20,
                    parameter_count=2,
                ),
            ),
            reason="skipped uncompiled nested classes",
            skipped=("src/Nested.java",),
        )
        for sink in (TranscriptSink(), ReviewSink()):
            rendered = sink.render(degraded_with_functions, NO_THRESHOLDS)
            lowered = rendered.lower()
            for forbidden_word in ("fail", "violation", "error", "must fix"):
                assert forbidden_word not in lowered


class TestTheArtifactSink:
    def test_it_produces_json_serializable_data(self):
        payload = ArtifactSink().render(measurement_with(14), NO_THRESHOLDS)
        assert json.dumps(payload)

    def test_it_carries_the_status_and_the_functions(self):
        payload = ArtifactSink().render(measurement_with(14), NO_THRESHOLDS)
        assert payload["status"] == RAN
        assert payload["functions"][0]["cyclomatic_complexity"] == 14

    def test_it_records_the_threshold_source_for_the_report(self):
        thresholds = Thresholds(cyclomatic_complexity=10, source="checkstyle.xml")
        payload = ArtifactSink().render(measurement_with(14), thresholds)
        assert payload["thresholds"]["source"] == "checkstyle.xml"


class TestEverySinkStatesWhatWasMeasured:
    """A sink that renders only the result cannot distinguish "this target has
    no functions" from "the range I was given selected none of them"."""

    def test_the_transcript_names_the_scope(self):
        rendered = TranscriptSink().render(
            Measurement(status=RAN), NO_THRESHOLDS, "File.py lines 3-4"
        )
        assert "File.py lines 3-4" in rendered
        assert "no functions" in rendered

    def test_the_review_sink_names_the_scope(self):
        rendered = ReviewSink().render(
            Measurement(status=RAN), NO_THRESHOLDS, "File.py lines 3-4"
        )
        assert "File.py lines 3-4" in rendered

    def test_the_artifact_carries_the_scope(self):
        payload = ArtifactSink().render(
            Measurement(status=RAN), NO_THRESHOLDS, "File.py lines 3-4"
        )
        assert payload["scope"] == "File.py lines 3-4"

    def test_a_caller_with_no_scope_to_state_invents_none(self):
        rendered = TranscriptSink().render(measurement_with(14), NO_THRESHOLDS)
        assert "scope:" not in rendered
        assert (
            ArtifactSink().render(measurement_with(14), NO_THRESHOLDS)["scope"] is None
        )

    def test_a_measurement_with_no_numbers_still_names_its_target(self):
        """The run that produced nothing is the one where "against what?" is
        the whole question. The artifact records the scope on this path, so a
        text sink that drops it makes two renderings of one run disagree."""
        unverified = Measurement(status=UNVERIFIED, reason="lizard is not installed")
        for sink in (TranscriptSink(), ReviewSink()):
            rendered = sink.render(unverified, NO_THRESHOLDS, "File.py lines 3-4")
            assert "File.py lines 3-4" in rendered
            assert "lizard is not installed" in rendered

    def test_a_measurement_with_no_numbers_and_no_scope_is_unchanged(self):
        """The control: a caller that states no scope still gets the bare
        status line, with no empty heading above it."""
        rendered = TranscriptSink().render(
            Measurement(status=UNVERIFIED, reason="needs compiled classes"),
            NO_THRESHOLDS,
        )
        assert rendered == "unverified: needs compiled classes"

    def test_the_scope_does_not_displace_the_measurement(self):
        rendered = TranscriptSink().render(
            measurement_with(14), NO_THRESHOLDS, "File.py lines 40-78"
        )
        assert "OrderService::applyDiscount" in rendered
        assert "File.py lines 40-78" in rendered


class TestTheArtifactSinkReportsUnreadableConfigs:
    def test_a_diagnostic_reaches_the_payload(self):
        thresholds = no_thresholds_because("pyproject.toml: max-complexity is 'ten'")
        payload = ArtifactSink().render(measurement_with(14), thresholds)
        assert payload["thresholds"]["diagnostics"] == [
            "pyproject.toml: max-complexity is 'ten'"
        ]

    def test_a_repo_declaring_nothing_carries_no_diagnostics(self):
        payload = ArtifactSink().render(measurement_with(14), NO_THRESHOLDS)
        assert payload["thresholds"]["diagnostics"] == []


class TestTheReviewSink:
    def test_it_leads_with_the_outlier(self):
        measurement = Measurement(
            status=RAN,
            functions=(
                FunctionMetric("low", "a.java", 1, 5, 2, 5, 0),
                FunctionMetric("high", "a.java", 10, 60, 21, 50, 3),
            ),
        )
        rendered = ReviewSink().render(measurement, NO_THRESHOLDS)
        assert rendered.index("high") < rendered.index("low")

    def test_it_labels_parameter_count_as_parameters(self):
        rendered = ReviewSink().render(measurement_with(14), NO_THRESHOLDS)
        assert "parameters 2" in rendered
        assert "nesting-proxy" not in rendered

    def test_a_degraded_measurement_shows_functions_and_the_reason(self):
        degraded = Measurement(
            status=DEGRADED,
            functions=(
                FunctionMetric(
                    name="incomplete::analyze",
                    path="src/Parser.java",
                    start_line=20,
                    end_line=45,
                    cyclomatic_complexity=8,
                    length=25,
                    parameter_count=1,
                ),
            ),
            reason="missing nested class definitions",
            skipped=("src/Nested.java",),
        )
        rendered = ReviewSink().render(degraded, NO_THRESHOLDS)
        assert "incomplete::analyze" in rendered
        assert "8" in rendered
        assert "degraded" in rendered
        assert "missing nested class definitions" in rendered
        assert "src/Nested.java" in rendered
