"""The gate rule, exhaustively: produce a measurement, or state why there
isn't one. Silence is the only thing that blocks.

Every test here runs against a Measurement value or None — no probe, no
subprocess. That is the point of injecting the probe elsewhere.
"""

from complexity_probe_gate import SILENCE, CycleGate, GateVerdict
from complexity_probe_measurement import (
    DEGRADED,
    RAN,
    UNVERIFIED,
    FunctionMetric,
    Measurement,
)


def a_measurement(status=RAN, reason=None):
    functions = (
        FunctionMetric(
            name="applyDiscount",
            path="OrderService.java",
            start_line=40,
            end_line=78,
            cyclomatic_complexity=14,
            length=38,
            parameter_count=2,
        ),
    )
    if status == RAN:
        return Measurement(status=status, functions=functions)
    return Measurement(status=status, functions=functions, reason=reason)


class TestOnlySilenceBlocks:
    def test_silence_with_an_available_probe_blocks(self):
        verdict = CycleGate().evaluate(measurement=None, probe_available=True)
        assert verdict.blocks is True
        assert verdict.status == SILENCE

    def test_a_ran_measurement_does_not_block(self):
        verdict = CycleGate().evaluate(a_measurement(), probe_available=True)
        assert verdict.blocks is False
        assert verdict.status == RAN

    def test_a_degraded_measurement_does_not_block(self):
        verdict = CycleGate().evaluate(
            a_measurement(DEGRADED, reason="time budget hit"),
            probe_available=True,
        )
        assert verdict.blocks is False
        assert verdict.status == DEGRADED

    def test_an_unverified_measurement_does_not_block(self):
        verdict = CycleGate().evaluate(
            a_measurement(UNVERIFIED, reason="needs compiled classes"),
            probe_available=True,
        )
        assert verdict.blocks is False
        assert verdict.status == UNVERIFIED


class TestTheBugThatBricksLanguages:
    """Spec §2.4 — blocking on absent measurement rather than on silence would
    permanently strand any language the probe cannot parse."""

    def test_silence_with_no_available_probe_does_not_block(self):
        verdict = CycleGate().evaluate(measurement=None, probe_available=False)
        assert verdict.blocks is False
        assert verdict.status == UNVERIFIED

    def test_and_it_says_why_rather_than_going_quiet(self):
        verdict = CycleGate().evaluate(measurement=None, probe_available=False)
        assert verdict.message


class TestTheMessageIsActionable:
    def test_a_block_says_what_to_do(self):
        verdict = CycleGate().evaluate(measurement=None, probe_available=True)
        assert "measure" in verdict.message.lower()

    def test_an_unverified_verdict_carries_the_measurement_reason(self):
        verdict = CycleGate().evaluate(
            a_measurement(UNVERIFIED, reason="needs compiled classes"),
            probe_available=True,
        )
        assert "needs compiled classes" in verdict.message


class TestTheVerdictIsData:
    def test_a_verdict_is_comparable(self):
        assert GateVerdict(blocks=False, status=RAN, message="x") == GateVerdict(
            blocks=False, status=RAN, message="x"
        )
