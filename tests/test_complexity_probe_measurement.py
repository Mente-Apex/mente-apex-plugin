"""The status invariant is the whole point: a non-`ran` measurement without a
reason is indistinguishable from silence, which is the failure being fixed."""

import pytest

from complexity_probe_measurement import (
    DEGRADED,
    RAN,
    UNVERIFIED,
    FunctionMetric,
    Measurement,
)


def a_function(cyclomatic_complexity=3):
    return FunctionMetric(
        name="OrderService::applyDiscount",
        path="src/OrderService.java",
        start_line=40,
        end_line=78,
        cyclomatic_complexity=cyclomatic_complexity,
        length=38,
        parameter_count=2,
    )


class TestTheStatusInvariant:
    def test_unverified_without_a_reason_is_rejected(self):
        with pytest.raises(ValueError, match="reason"):
            Measurement(status=UNVERIFIED)

    def test_degraded_without_a_reason_is_rejected(self):
        with pytest.raises(ValueError, match="reason"):
            Measurement(status=DEGRADED, functions=(a_function(),))

    def test_unverified_with_a_reason_is_accepted(self):
        measurement = Measurement(status=UNVERIFIED, reason="no probe for kotlin")
        assert measurement.reason == "no probe for kotlin"

    def test_ran_needs_no_reason(self):
        measurement = Measurement(status=RAN, functions=(a_function(),))
        assert measurement.reason is None

    def test_an_unknown_status_is_rejected(self):
        with pytest.raises(ValueError, match="status"):
            Measurement(status="fine", reason="whatever")


class TestWhatTheSinksAsk:
    def test_ran_with_no_functions_still_counts_as_measured(self):
        """An empty diff measured is a real answer, not an absent one."""
        measurement = Measurement(status=RAN)
        assert measurement.has_numbers is True
        assert measurement.is_ran is True

    def test_unverified_has_no_numbers(self):
        measurement = Measurement(status=UNVERIFIED, reason="lizard absent")
        assert measurement.has_numbers is False

    def test_degraded_has_numbers_and_names_what_was_skipped(self):
        measurement = Measurement(
            status=DEGRADED,
            functions=(a_function(),),
            reason="time budget hit",
            skipped=("src/legacy/",),
        )
        assert measurement.has_numbers is True
        assert measurement.skipped == ("src/legacy/",)
