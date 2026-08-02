"""The only module that knows lizard exists.

Separate from the measurement types because swapping the tool (or adding a
second one for a language lizard cannot read) must not touch the vocabulary
every other module depends on. The subprocess call is injected as `runner` so
probe behavior — availability, crashes, empty input — is testable without the
tool installed.
"""

import csv
import io
import shutil
import subprocess

from complexity_probe_measurement import (
    RAN,
    UNVERIFIED,
    FunctionMetric,
    Measurement,
)

# lizard --csv emits no header. Column order, verified against lizard 1.23.0:
# nloc, ccn, token_count, parameter_count, length, location, file, name,
# long_name, start_line, end_line
_COLUMN_COUNT = 11
_COLUMN_CCN = 1
_COLUMN_PARAMETER_COUNT = 3
_COLUMN_LENGTH = 4
_COLUMN_FILE = 6
_COLUMN_NAME = 7
_COLUMN_START_LINE = 9
_COLUMN_END_LINE = 10


def parse_lizard_csv(csv_text: str) -> tuple[FunctionMetric, ...]:
    """Rows that do not have the expected shape are skipped, not fatal — a
    single odd line must not cost the whole measurement."""
    metrics = []
    for row in csv.reader(io.StringIO(csv_text)):
        if len(row) < _COLUMN_COUNT:
            continue
        try:
            metrics.append(
                FunctionMetric(
                    name=row[_COLUMN_NAME],
                    path=row[_COLUMN_FILE],
                    start_line=int(row[_COLUMN_START_LINE]),
                    end_line=int(row[_COLUMN_END_LINE]),
                    cyclomatic_complexity=int(row[_COLUMN_CCN]),
                    length=int(row[_COLUMN_LENGTH]),
                    parameter_count=int(row[_COLUMN_PARAMETER_COUNT]),
                )
            )
        except ValueError:
            continue
    return tuple(metrics)


class SubprocessLizardRunner:
    """Resolves lizard from PATH, falling back to uv's ephemeral resolution."""

    def is_available(self) -> bool:
        return shutil.which("lizard") is not None or shutil.which("uv") is not None

    def _command(self) -> list[str]:
        if shutil.which("lizard"):
            return ["lizard", "--csv"]
        return ["uv", "run", "--with", "lizard", "lizard", "--csv"]

    def run(self, paths) -> str:
        completed = subprocess.run(
            self._command() + list(paths),
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.stdout


class LizardProbe:
    """Source-level complexity. Runs at every tier, including per-cycle."""

    name = "lizard"

    def __init__(self, runner=None):
        self._runner = runner if runner is not None else SubprocessLizardRunner()

    def is_available(self) -> bool:
        return self._runner.is_available()

    def measure(self, paths) -> Measurement:
        requested_paths = list(paths)
        if not requested_paths:
            return Measurement(status=RAN)
        if not self._runner.is_available():
            return Measurement(
                status=UNVERIFIED,
                reason="lizard is not installed and uv is not available to fetch it",
            )
        try:
            stdout = self._runner.run(requested_paths)
        except OSError as error:
            return Measurement(
                status=UNVERIFIED, reason=f"lizard could not be run: {error}"
            )
        return Measurement(status=RAN, functions=parse_lizard_csv(stdout))
