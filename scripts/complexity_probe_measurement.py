"""The measurement vocabulary, with the one invariant that makes the gate
possible: a non-`ran` status must say why.

Kept separate from every producer and consumer because "what a measurement is"
and "how we obtain one" are different reasons to change — the lizard parser,
the sinks and the gate all depend on these types and none of them on each
other. See docs/status-vocabulary.md for the vocabulary itself.
"""

from dataclasses import dataclass, field

RAN = "ran"
DEGRADED = "degraded"
UNVERIFIED = "unverified"

VALID_STATUSES = (RAN, DEGRADED, UNVERIFIED)


@dataclass(frozen=True)
class FunctionMetric:
    """One function's measured shape. Numbers only — no judgment."""

    name: str
    path: str
    start_line: int
    end_line: int
    cyclomatic_complexity: int
    length: int
    parameter_count: int


@dataclass(frozen=True)
class Measurement:
    """The result of asking a probe to measure something.

    `reason` is mandatory for anything other than `ran`: "did not run" without
    a cause reads exactly like silence, and silence is the failure this whole
    design exists to catch.
    """

    status: str
    functions: tuple[FunctionMetric, ...] = ()
    reason: str | None = None
    skipped: tuple[str, ...] = field(default=())

    def __post_init__(self):
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"unknown status {self.status!r}; expected one of {VALID_STATUSES}"
            )
        if self.status != RAN and not self.reason:
            raise ValueError(
                f"a {self.status!r} measurement must carry a reason — "
                "a reasonless gap is indistinguishable from silence"
            )

    @property
    def is_ran(self) -> bool:
        return self.status == RAN

    @property
    def has_numbers(self) -> bool:
        """True when the probe actually executed, even if it found nothing."""
        return self.status in (RAN, DEGRADED)
