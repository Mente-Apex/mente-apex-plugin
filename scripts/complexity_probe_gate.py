"""The gate rule and nothing else.

Deliberately imports no probe, no subprocess and no tool name: the gate rules
on whether a check was performed, never on what it found, so it has no reason
to know how measuring works. That separation is what makes every rule below
testable against a plain value.

The rule (spec §2.3): produce a measurement, or state why there isn't one.
Silence is the only thing that blocks.
"""

from dataclasses import dataclass

from complexity_probe_measurement import UNVERIFIED

SILENCE = "silence"

_BLOCK_MESSAGE = (
    "REFACTOR produced no measurement and the probe was available. "
    "Measure the changed functions, or state why you cannot."
)
_NO_PROBE_MESSAGE = (
    "No probe was available for this target, so nothing was measured. "
    "Recorded as unverified; not blocking."
)


@dataclass(frozen=True)
class GateVerdict:
    """What the gate decided, and why — never a judgment on the code."""

    blocks: bool
    status: str
    message: str


class CycleGate:
    """Decides `ran` / `degraded` / `unverified` / silence."""

    def evaluate(self, measurement, probe_available: bool) -> GateVerdict:
        if measurement is not None:
            return GateVerdict(
                blocks=False,
                status=measurement.status,
                message=self._describe(measurement),
            )
        if probe_available:
            return GateVerdict(blocks=True, status=SILENCE, message=_BLOCK_MESSAGE)
        return GateVerdict(blocks=False, status=UNVERIFIED, message=_NO_PROBE_MESSAGE)

    def _describe(self, measurement) -> str:
        if measurement.is_ran:
            return f"measured {len(measurement.functions)} function(s)"
        return f"{measurement.status}: {measurement.reason}"
