# Cycle-Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the TDD REFACTOR step produce measured evidence instead of prose, blocking only when it produces nothing at all.

**Architecture:** A complexity probe (lizard) feeds three sinks — the TDD transcript, the Phase 0 audit artifact, and on-demand chunk review. A gate reads whether a measurement was produced, never what it found. Five narrow seams (probe, threshold source, sink, tier map, tool advisory) are injected, so every verdict test runs against a stub with no subprocess.

**Tech Stack:** Python 3.14, uv, pytest, `lizard` 1.23+. Flat modules in `scripts/`, imported by bare name (`tests/conftest.py` puts `scripts/` on `sys.path`). Mirrors the existing `mutation_gate*.py` family.

**Spec:** [`../specs/2026-08-02-cycle-gate-verdict-design.md`](../specs/2026-08-02-cycle-gate-verdict-design.md)

## Global Constraints

- **The gate rule, verbatim:** "Produce a measurement, or state why there isn't one. Silence is the only thing that blocks." (spec §2.3)
- **`unverified` and `degraded` always carry a reason.** A reasonless non-`ran` status is a bug, enforced at construction.
- **The plugin ships no default thresholds.** Read what the target repo declares; where it declares none, report the distribution and assert nothing. (spec §4.2)
- **Numbers never decide a verdict.** A threshold breach is a place to look, never a finding on its own.
- **Never blocks a human.** Only the TDD cycle path can block; chunk review and the audit never do. (spec §3)
- **Module docstrings state why the file exists *separately*** — the house style in `scripts/mutation_gate_backends.py`.
- **No single-letter or abbreviated names**, including in comprehensions.
- **Formatting:** `uv run black .`, line length 88. **Lint:** `uv run ruff check --fix .` — remaining lint is a blocker.
- **Python 3.14**, `requires-python = ">=3.14"`.
- Status strings are exactly `"ran"`, `"degraded"`, `"unverified"` — the vocabulary in `docs/status-vocabulary.md`.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/complexity_probe_measurement.py` | The data types and the status invariant. No I/O. |
| `scripts/complexity_probe_lizard.py` | Running lizard and parsing its CSV. The only file that knows lizard exists. |
| `scripts/complexity_probe_probes.py` | Registry — which probes exist, and the tier map. |
| `scripts/complexity_probe_scope.py` | Turning a scope argument into file paths. |
| `scripts/complexity_probe_gate.py` | The verdict. Knows nothing about any tool. |
| `scripts/complexity_probe_thresholds.py` | Reading limits the target repo already declares. |
| `scripts/complexity_probe_advisory.py` | What a build system needs to supply a missing tool. |
| `scripts/complexity_probe_sinks.py` | Rendering a measurement for transcript / artifact / review. |
| `scripts/complexity_probe.py` | CLI entry point and wiring. |

Tasks 1-8 are pure Python with no skill-file changes. Tasks 9-11 wire the skills.

---

### Task 1: Measurement types and the status invariant

**Files:**
- Create: `scripts/complexity_probe_measurement.py`
- Test: `tests/test_complexity_probe_measurement.py`

**Interfaces:**
- Consumes: nothing
- Produces: `RAN`, `DEGRADED`, `UNVERIFIED` (str constants); `FunctionMetric(name, path, start_line, end_line, cyclomatic_complexity, length, parameter_count)`; `Measurement(status, functions=(), reason=None, skipped=())` with properties `is_ran`, `has_numbers`; raises `ValueError` when a non-`ran` status has no reason.

- [ ] **Step 1: Write the failing test**

```python
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
        measurement = Measurement(
            status=UNVERIFIED, reason="no probe for kotlin"
        )
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_complexity_probe_measurement.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'complexity_probe_measurement'`

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_complexity_probe_measurement.py -v`
Expected: PASS — 8 tests

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black scripts/complexity_probe_measurement.py tests/test_complexity_probe_measurement.py
uv run ruff check --fix scripts/complexity_probe_measurement.py tests/test_complexity_probe_measurement.py
git add scripts/complexity_probe_measurement.py tests/test_complexity_probe_measurement.py
git commit -m "feat(probe): measurement types with a mandatory reason for any gap"
```

---

### Task 2: The lizard probe

**Files:**
- Create: `scripts/complexity_probe_lizard.py`
- Test: `tests/test_complexity_probe_lizard.py`
- Modify: `pyproject.toml` (add `lizard` to `[dependency-groups] dev`)
- Uses (already committed): `tests/fixtures/probe/java/{Shape,Compact,Flexible}.java`

**Interfaces:**
- Consumes: `Measurement`, `FunctionMetric`, `RAN`, `UNVERIFIED` from Task 1
- Produces: `LizardProbe(runner=None)` with `.name == "lizard"`, `.is_available() -> bool`, `.measure(paths) -> Measurement`; `parse_lizard_csv(csv_text) -> tuple[FunctionMetric, ...]`

**Background the engineer needs:** lizard's `--csv` emits **no header row** and eleven columns in this order: `nloc, ccn, token_count, parameter_count, length, location, file, name, long_name, start_line, end_line`. Verified against lizard 1.23.0. `location` is a composite (`Name@start-end@file`) and is ignored — columns 6-10 carry the same data cleanly.

- [ ] **Step 1: Write the failing test**

```python
"""The parser is tested against captured CSV; the probe is tested against a
stub runner. One real-lizard test runs over the committed Java 25 fixtures —
that one is the regression net for "can we still parse this language".
"""

from pathlib import Path

from complexity_probe_lizard import LizardProbe, parse_lizard_csv
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
        by_name = {
            metric.name: metric for metric in measurement.functions
        }
        assert by_name["AreaCalculator::area"].cyclomatic_complexity == 6
        assert by_name["main"].cyclomatic_complexity == 7
        assert by_name["Account::Account"].cyclomatic_complexity == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_complexity_probe_lizard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'complexity_probe_lizard'`

- [ ] **Step 3: Declare the dependency**

```bash
uv add --dev lizard
```

- [ ] **Step 4: Write minimal implementation**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_complexity_probe_lizard.py -v`
Expected: PASS — 10 tests, none skipped (lizard is now a dev dependency)

- [ ] **Step 6: Format, lint, commit**

```bash
uv run black scripts/complexity_probe_lizard.py tests/test_complexity_probe_lizard.py
uv run ruff check --fix scripts/complexity_probe_lizard.py tests/test_complexity_probe_lizard.py
git add scripts/complexity_probe_lizard.py tests/test_complexity_probe_lizard.py pyproject.toml uv.lock
git commit -m "feat(probe): lizard probe with an injected runner and CSV parsing"
```

---

### Task 3: The gate verdict

**Files:**
- Create: `scripts/complexity_probe_gate.py`
- Test: `tests/test_complexity_probe_gate.py`

**Interfaces:**
- Consumes: `Measurement`, `RAN`, `DEGRADED`, `UNVERIFIED` from Task 1
- Produces: `GateVerdict(blocks: bool, status: str, message: str)`; `CycleGate().evaluate(measurement, probe_available) -> GateVerdict`; constant `SILENCE = "silence"`

**This is the most important task in the plan.** It encodes the spec's one rule, and it must not import any probe, tool, or subprocess.

- [ ] **Step 1: Write the failing test**

```python
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
        assert GateVerdict(
            blocks=False, status=RAN, message="x"
        ) == GateVerdict(blocks=False, status=RAN, message="x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_complexity_probe_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'complexity_probe_gate'`

- [ ] **Step 3: Write minimal implementation**

```python
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
            return GateVerdict(
                blocks=True, status=SILENCE, message=_BLOCK_MESSAGE
            )
        return GateVerdict(
            blocks=False, status=UNVERIFIED, message=_NO_PROBE_MESSAGE
        )

    def _describe(self, measurement) -> str:
        if measurement.is_ran:
            return f"measured {len(measurement.functions)} function(s)"
        return f"{measurement.status}: {measurement.reason}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_complexity_probe_gate.py -v`
Expected: PASS — 10 tests

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black scripts/complexity_probe_gate.py tests/test_complexity_probe_gate.py
uv run ruff check --fix scripts/complexity_probe_gate.py tests/test_complexity_probe_gate.py
git add scripts/complexity_probe_gate.py tests/test_complexity_probe_gate.py
git commit -m "feat(probe): the cycle-gate verdict — only silence blocks"
```

---

### Task 4: Scope resolution

**Files:**
- Create: `scripts/complexity_probe_scope.py`
- Test: `tests/test_complexity_probe_scope.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `ScopeSelection(paths: tuple[str, ...], line_range: tuple[int, int] | None, description: str)`; `resolve_scope(argument, repo_root, git_runner=None) -> ScopeSelection`; `parse_range(argument) -> tuple[str, int, int] | None`

**Background:** `--scope` values mirror `scripts/mutation_gate.py` (`merge-base`, `working-tree`, `full`). A bare argument may also be a path or a `File.java:40-120` range — the two forms spec §4.3 marks as new.

- [ ] **Step 1: Write the failing test**

```python
"""Scope resolution, including the two forms the spec adds: a bare invocation
meaning the uncommitted working tree, and a line range naming one function."""

from complexity_probe_scope import ScopeSelection, parse_range, resolve_scope


class StubGitRunner:
    def __init__(self, changed_files=("src/OrderService.java",)):
        self.changed_files = list(changed_files)
        self.calls = []

    def changed_paths(self, mode):
        self.calls.append(mode)
        return list(self.changed_files)


class TestParsingARange:
    def test_a_range_is_split_into_path_and_bounds(self):
        assert parse_range("OrderService.java:40-120") == (
            "OrderService.java",
            40,
            120,
        )

    def test_a_bare_path_is_not_a_range(self):
        assert parse_range("src/orders/") is None

    def test_a_windows_style_drive_letter_is_not_a_range(self):
        assert parse_range("C:/src/OrderService.java") is None

    def test_a_reversed_range_is_rejected(self):
        assert parse_range("OrderService.java:120-40") is None


class TestResolvingScope:
    def test_no_argument_means_the_uncommitted_working_tree(self):
        git_runner = StubGitRunner()
        selection = resolve_scope(None, repo_root=".", git_runner=git_runner)
        assert git_runner.calls == ["working-tree"]
        assert selection.paths == ("src/OrderService.java",)

    def test_working_tree_is_the_same_as_no_argument(self):
        git_runner = StubGitRunner()
        selection = resolve_scope(
            "working-tree", repo_root=".", git_runner=git_runner
        )
        assert selection.paths == ("src/OrderService.java",)

    def test_merge_base_asks_git_for_the_branch_diff(self):
        git_runner = StubGitRunner()
        resolve_scope("merge-base", repo_root=".", git_runner=git_runner)
        assert git_runner.calls == ["merge-base"]

    def test_full_is_the_repo_root_and_asks_git_nothing(self):
        git_runner = StubGitRunner()
        selection = resolve_scope("full", repo_root="/repo", git_runner=git_runner)
        assert selection.paths == ("/repo",)
        assert git_runner.calls == []

    def test_a_path_is_taken_literally(self):
        selection = resolve_scope(
            "src/orders/", repo_root=".", git_runner=StubGitRunner()
        )
        assert selection.paths == ("src/orders/",)
        assert selection.line_range is None

    def test_a_range_keeps_its_bounds(self):
        selection = resolve_scope(
            "OrderService.java:40-120", repo_root=".", git_runner=StubGitRunner()
        )
        assert selection.paths == ("OrderService.java",)
        assert selection.line_range == (40, 120)

    def test_an_empty_working_tree_yields_no_paths(self):
        selection = resolve_scope(
            None, repo_root=".", git_runner=StubGitRunner(changed_files=())
        )
        assert selection.paths == ()

    def test_every_selection_describes_itself_for_the_report(self):
        selection = resolve_scope(
            "full", repo_root="/repo", git_runner=StubGitRunner()
        )
        assert isinstance(selection, ScopeSelection)
        assert selection.description
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_complexity_probe_scope.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'complexity_probe_scope'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Turning a scope argument into paths.

Separate from the probe because "which files are in play" changes for reasons
that have nothing to do with how a file is measured — a new scope form, a
different VCS. `--scope` keeps the same vocabulary as scripts/mutation_gate.py
so the two sensors are asked for a target the same way.
"""

import re
import subprocess
from dataclasses import dataclass

WORKING_TREE = "working-tree"
MERGE_BASE = "merge-base"
FULL = "full"

# "path:40-120" — requires a digit-hyphen-digit tail so a Windows drive letter
# or a bare colon in a path is not mistaken for a range.
_RANGE_PATTERN = re.compile(r"^(?P<path>.+):(?P<start>\d+)-(?P<end>\d+)$")


@dataclass(frozen=True)
class ScopeSelection:
    paths: tuple[str, ...]
    line_range: tuple[int, int] | None
    description: str


def parse_range(argument: str):
    """Returns (path, start_line, end_line), or None when not a range."""
    match = _RANGE_PATTERN.match(argument)
    if not match:
        return None
    start_line = int(match.group("start"))
    end_line = int(match.group("end"))
    if start_line > end_line:
        return None
    return match.group("path"), start_line, end_line


class GitRunner:
    """The git queries scope resolution needs, isolated so tests can stub them."""

    def __init__(self, repo_root="."):
        self._repo_root = repo_root

    def changed_paths(self, mode: str) -> list[str]:
        if mode == MERGE_BASE:
            command = ["git", "diff", "--name-only", "--diff-filter=d", "origin/HEAD..."]
        else:
            command = ["git", "diff", "--name-only", "--diff-filter=d", "HEAD"]
        completed = subprocess.run(
            command,
            cwd=self._repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return [line for line in completed.stdout.splitlines() if line.strip()]


def resolve_scope(argument, repo_root=".", git_runner=None) -> ScopeSelection:
    resolver = git_runner if git_runner is not None else GitRunner(repo_root)

    if argument is None or argument == WORKING_TREE:
        paths = tuple(resolver.changed_paths(WORKING_TREE))
        return ScopeSelection(
            paths=paths,
            line_range=None,
            description="uncommitted changes in the working tree",
        )

    if argument == MERGE_BASE:
        paths = tuple(resolver.changed_paths(MERGE_BASE))
        return ScopeSelection(
            paths=paths, line_range=None, description="changes on this branch"
        )

    if argument == FULL:
        return ScopeSelection(
            paths=(repo_root,), line_range=None, description="the whole repository"
        )

    parsed_range = parse_range(argument)
    if parsed_range:
        path, start_line, end_line = parsed_range
        return ScopeSelection(
            paths=(path,),
            line_range=(start_line, end_line),
            description=f"{path} lines {start_line}-{end_line}",
        )

    return ScopeSelection(paths=(argument,), line_range=None, description=argument)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_complexity_probe_scope.py -v`
Expected: PASS — 13 tests

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black scripts/complexity_probe_scope.py tests/test_complexity_probe_scope.py
uv run ruff check --fix scripts/complexity_probe_scope.py tests/test_complexity_probe_scope.py
git add scripts/complexity_probe_scope.py tests/test_complexity_probe_scope.py
git commit -m "feat(probe): scope resolution with working-tree default and line ranges"
```

---

### Task 5: Threshold sources

**Files:**
- Create: `scripts/complexity_probe_thresholds.py`
- Test: `tests/test_complexity_probe_thresholds.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `Thresholds(cyclomatic_complexity: int | None, source: str)`; `CheckstyleThresholds`, `PmdThresholds`, `RuffThresholds`, `EslintThresholds`, `NullThresholds` — each with `.thresholds_for(repo_root) -> Thresholds | None`; `discover_thresholds(repo_root, sources=None) -> Thresholds`

**The constraint that matters:** when no config declares a limit, the result is `Thresholds(cyclomatic_complexity=None, source="none declared")` — **never an invented number**.

- [ ] **Step 1: Write the failing test**

```python
"""Thresholds come from the target repo or they do not exist. The plugin
ships no numbers of its own (spec §4.2)."""

from complexity_probe_thresholds import (
    CheckstyleThresholds,
    EslintThresholds,
    NullThresholds,
    RuffThresholds,
    discover_thresholds,
)


class TestReadingWhatTheRepoDeclares:
    def test_checkstyle_cyclomatic_complexity_is_read(self, tmp_path):
        (tmp_path / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n'
            "<module name=\"Checker\">\n"
            '  <module name="CyclomaticComplexity">\n'
            '    <property name="max" value="12"/>\n'
            "  </module>\n"
            "</module>\n"
        )
        thresholds = CheckstyleThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 12
        assert "checkstyle" in thresholds.source

    def test_ruff_mccabe_max_complexity_is_read(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.ruff.lint.mccabe]\nmax-complexity = 8\n"
        )
        thresholds = RuffThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 8

    def test_eslint_complexity_rule_is_read(self, tmp_path):
        (tmp_path / ".eslintrc.json").write_text(
            '{"rules": {"complexity": ["error", 10]}}'
        )
        thresholds = EslintThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 10


class TestAbsence:
    def test_a_repo_declaring_nothing_yields_no_number(self, tmp_path):
        thresholds = discover_thresholds(tmp_path)
        assert thresholds.cyclomatic_complexity is None
        assert "none declared" in thresholds.source

    def test_checkstyle_without_the_rule_yields_nothing(self, tmp_path):
        (tmp_path / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n<module name="Checker"/>\n'
        )
        assert CheckstyleThresholds().thresholds_for(tmp_path) is None

    def test_malformed_config_is_absence_not_a_crash(self, tmp_path):
        (tmp_path / ".eslintrc.json").write_text("{not json")
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_the_null_source_always_yields_nothing(self, tmp_path):
        assert NullThresholds().thresholds_for(tmp_path) is None


class TestDiscoveryOrder:
    def test_the_first_source_that_declares_a_number_wins(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.ruff.lint.mccabe]\nmax-complexity = 8\n"
        )
        (tmp_path / ".eslintrc.json").write_text(
            '{"rules": {"complexity": ["error", 10]}}'
        )
        thresholds = discover_thresholds(
            tmp_path, sources=(RuffThresholds(), EslintThresholds())
        )
        assert thresholds.cyclomatic_complexity == 8

    def test_adding_a_source_needs_no_edit_to_discovery(self, tmp_path):
        class FakeSource:
            def thresholds_for(self, repo_root):
                from complexity_probe_thresholds import Thresholds

                return Thresholds(cyclomatic_complexity=99, source="fake")

        thresholds = discover_thresholds(tmp_path, sources=(FakeSource(),))
        assert thresholds.cyclomatic_complexity == 99
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_complexity_probe_thresholds.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'complexity_probe_thresholds'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Where a project's declared complexity limits are read from.

Separate because this changes when a *build tool* changes its config format —
nothing to do with how code is measured or how a verdict is reached. Adding a
tool is adding a class and one registry entry; `discover_thresholds` never
needs editing.

The plugin ships no numbers. A repo that declares no limit gets no limit, which
is what keeps docs/clean-code-standard.md's rejection of universal numbers
intact rather than quietly contradicted.
"""

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Thresholds:
    cyclomatic_complexity: int | None
    source: str


NO_THRESHOLDS = Thresholds(cyclomatic_complexity=None, source="none declared")

_CHECKSTYLE_COMPLEXITY = re.compile(
    r'<module\s+name="CyclomaticComplexity".*?'
    r'<property\s+name="max"\s+value="(?P<max>\d+)"',
    re.DOTALL,
)


class CheckstyleThresholds:
    def thresholds_for(self, repo_root):
        config_path = Path(repo_root) / "checkstyle.xml"
        if not config_path.exists():
            return None
        match = _CHECKSTYLE_COMPLEXITY.search(config_path.read_text())
        if not match:
            return None
        return Thresholds(
            cyclomatic_complexity=int(match.group("max")), source="checkstyle.xml"
        )


class PmdThresholds:
    def thresholds_for(self, repo_root):
        config_path = Path(repo_root) / "pmd-ruleset.xml"
        if not config_path.exists():
            return None
        match = re.search(
            r'<property\s+name="(?:classReportLevel|methodReportLevel)"\s+'
            r'value="(?P<max>\d+)"',
            config_path.read_text(),
        )
        if not match:
            return None
        return Thresholds(
            cyclomatic_complexity=int(match.group("max")), source="pmd-ruleset.xml"
        )


class RuffThresholds:
    def thresholds_for(self, repo_root):
        config_path = Path(repo_root) / "pyproject.toml"
        if not config_path.exists():
            return None
        try:
            parsed = tomllib.loads(config_path.read_text())
        except tomllib.TOMLDecodeError:
            return None
        mccabe = (
            parsed.get("tool", {})
            .get("ruff", {})
            .get("lint", {})
            .get("mccabe", {})
        )
        maximum = mccabe.get("max-complexity")
        if maximum is None:
            return None
        return Thresholds(
            cyclomatic_complexity=int(maximum),
            source="pyproject.toml [tool.ruff.lint.mccabe]",
        )


class EslintThresholds:
    def thresholds_for(self, repo_root):
        config_path = Path(repo_root) / ".eslintrc.json"
        if not config_path.exists():
            return None
        try:
            parsed = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            return None
        rule = parsed.get("rules", {}).get("complexity")
        if isinstance(rule, list) and len(rule) > 1:
            try:
                return Thresholds(
                    cyclomatic_complexity=int(rule[1]), source=".eslintrc.json"
                )
            except (TypeError, ValueError):
                return None
        return None


class NullThresholds:
    """The honest default: this project declares nothing."""

    def thresholds_for(self, repo_root):
        return None


def default_threshold_sources():
    """The sources a normal run consults, in order."""
    return (
        CheckstyleThresholds(),
        PmdThresholds(),
        RuffThresholds(),
        EslintThresholds(),
    )


def discover_thresholds(repo_root, sources=None) -> Thresholds:
    for source in sources if sources is not None else default_threshold_sources():
        thresholds = source.thresholds_for(repo_root)
        if thresholds is not None:
            return thresholds
    return NO_THRESHOLDS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_complexity_probe_thresholds.py -v`
Expected: PASS — 10 tests

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black scripts/complexity_probe_thresholds.py tests/test_complexity_probe_thresholds.py
uv run ruff check --fix scripts/complexity_probe_thresholds.py tests/test_complexity_probe_thresholds.py
git add scripts/complexity_probe_thresholds.py tests/test_complexity_probe_thresholds.py
git commit -m "feat(probe): read declared thresholds, invent none"
```

---

### Task 6: Tool advisories

**Files:**
- Create: `scripts/complexity_probe_advisory.py`
- Test: `tests/test_complexity_probe_advisory.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `Advice(tool: str, action: str, snippet: str, note: str)`; `detect_build_system(repo_root) -> str` returning `"gradle-kotlin" | "gradle-groovy" | "maven" | "unknown"`; `advice_for(tool, repo_root, build_system=None) -> Advice | None`; constants `ABSENT`, `TOO_OLD`

**The rule:** *absent* and *too old* are different verdicts pointing at different fixes — install versus upgrade. No version numbers appear anywhere; the note states the class-file 69 constraint instead.

- [ ] **Step 1: Write the failing test**

```python
"""Advice makes `unverified` actionable. It never blocks, never invents a
version, and distinguishes install from upgrade."""

from complexity_probe_advisory import (
    ABSENT,
    TOO_OLD,
    advice_for,
    detect_build_system,
)


class TestDetectingTheBuildSystem:
    def test_gradle_kotlin_dsl(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("plugins { java }")
        assert detect_build_system(tmp_path) == "gradle-kotlin"

    def test_gradle_groovy_dsl(self, tmp_path):
        (tmp_path / "build.gradle").write_text("plugins { id 'java' }")
        assert detect_build_system(tmp_path) == "gradle-groovy"

    def test_maven(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        assert detect_build_system(tmp_path) == "maven"

    def test_nothing_recognizable(self, tmp_path):
        assert detect_build_system(tmp_path) == "unknown"

    def test_kotlin_dsl_wins_when_both_gradle_files_exist(self, tmp_path):
        (tmp_path / "build.gradle").write_text("")
        (tmp_path / "build.gradle.kts").write_text("")
        assert detect_build_system(tmp_path) == "gradle-kotlin"


class TestAdviceContent:
    def test_gradle_kotlin_archunit_names_the_test_dependency(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        advice = advice_for("archunit", tmp_path, reason=ABSENT)
        assert "testImplementation" in advice.snippet
        assert "com.tngtech.archunit" in advice.snippet

    def test_maven_pit_names_the_plugin(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        advice = advice_for("pit", tmp_path, reason=ABSENT)
        assert "pitest-maven" in advice.snippet

    def test_jacoco_on_gradle_is_the_built_in_plugin(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        advice = advice_for("jacoco", tmp_path, reason=ABSENT)
        assert "jacoco" in advice.snippet


class TestNoInventedVersions:
    def test_no_advice_contains_a_version_literal(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        for tool in ("archunit", "pit", "jacoco", "checkstyle", "pmd"):
            advice = advice_for(tool, tmp_path, reason=ABSENT)
            assert "<version>" in advice.snippet or ":" in advice.snippet
            assert not any(
                part.replace(".", "").isdigit() and "." in part
                for part in advice.snippet.split('"')
            ), f"{tool} advice appears to pin a version"


class TestInstallVersusUpgrade:
    def test_absent_advises_adding_it(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        advice = advice_for("pit", tmp_path, reason=ABSENT)
        assert advice.action == "add"

    def test_too_old_advises_upgrading_not_adding(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        advice = advice_for("pit", tmp_path, reason=TOO_OLD)
        assert advice.action == "upgrade"
        assert "class-file 69" in advice.note


class TestSilenceRatherThanGuessing:
    def test_an_unknown_build_system_yields_no_advice(self, tmp_path):
        assert advice_for("pit", tmp_path, reason=ABSENT) is None

    def test_an_unknown_tool_yields_no_advice(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        assert advice_for("nosuchtool", tmp_path, reason=ABSENT) is None

    def test_a_jdk_bundled_tool_needs_no_advice(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        assert advice_for("jdeps", tmp_path, reason=ABSENT) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_complexity_probe_advisory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'complexity_probe_advisory'`

- [ ] **Step 3: Write minimal implementation**

```python
"""What a build needs to supply a tool that is missing.

Its own module because build coordinates and JDK-compatibility floors move on
someone else's release schedule; none of that should reach the probe, the sink
or the gate.

No version numbers live here on purpose. Every bytecode-reading tool must be
new enough to parse class-file 69 (Java 25), and a number written into source
goes stale silently — so the advice states the constraint and leaves the pin to
the reader.
"""

from dataclasses import dataclass
from pathlib import Path

ABSENT = "absent"
TOO_OLD = "too-old"

GRADLE_KOTLIN = "gradle-kotlin"
GRADLE_GROOVY = "gradle-groovy"
MAVEN = "maven"
UNKNOWN = "unknown"

_CLASS_FILE_NOTE = (
    "Must be new enough to read class-file 69 (Java 25); pin the current "
    "release rather than an older known-good version."
)

# tool -> build system -> snippet. A tool absent from this table gets no
# advice, which is the correct answer for jdeps (JDK-bundled) and lizard
# (a source-reading Python tool, never a build dependency).
_SNIPPETS = {
    "archunit": {
        GRADLE_KOTLIN: 'testImplementation("com.tngtech.archunit:archunit-junit5:<version>")',
        GRADLE_GROOVY: "testImplementation 'com.tngtech.archunit:archunit-junit5:<version>'",
        MAVEN: "<dependency> com.tngtech.archunit:archunit-junit5, <scope>test</scope>",
    },
    "pit": {
        GRADLE_KOTLIN: 'id("info.solidsoft.pitest") + testImplementation("org.pitest:pitest-junit5-plugin:<version>")',
        GRADLE_GROOVY: "id 'info.solidsoft.pitest' + testImplementation 'org.pitest:pitest-junit5-plugin:<version>'",
        MAVEN: "<plugin> org.pitest:pitest-maven, with org.pitest:pitest-junit5-plugin as a plugin dependency",
    },
    "jacoco": {
        GRADLE_KOTLIN: "plugins { jacoco }  // built in to Gradle",
        GRADLE_GROOVY: "plugins { jacoco }  // built in to Gradle",
        MAVEN: "<plugin> org.jacoco:jacoco-maven-plugin",
    },
    "checkstyle": {
        GRADLE_KOTLIN: "plugins { checkstyle }  // built in to Gradle",
        GRADLE_GROOVY: "plugins { checkstyle }  // built in to Gradle",
        MAVEN: "<plugin> org.apache.maven.plugins:maven-checkstyle-plugin",
    },
    "pmd": {
        GRADLE_KOTLIN: "plugins { pmd }  // built in to Gradle",
        GRADLE_GROOVY: "plugins { pmd }  // built in to Gradle",
        MAVEN: "<plugin> org.apache.maven.plugins:maven-pmd-plugin",
    },
    "spotbugs": {
        GRADLE_KOTLIN: 'id("com.github.spotbugs")',
        GRADLE_GROOVY: "id 'com.github.spotbugs'",
        MAVEN: "<plugin> com.github.spotbugs:spotbugs-maven-plugin",
    },
    "spring-modulith": {
        GRADLE_KOTLIN: 'testImplementation("org.springframework.modulith:spring-modulith-starter-test")  // version from the Boot BOM',
        GRADLE_GROOVY: "testImplementation 'org.springframework.modulith:spring-modulith-starter-test'  // version from the Boot BOM",
        MAVEN: "<dependency> org.springframework.modulith:spring-modulith-starter-test, version from the Boot BOM",
    },
}

# Tools that read bytecode, and so carry the class-file 69 caveat.
_BYTECODE_TOOLS = ("archunit", "pit", "jacoco", "spotbugs")


@dataclass(frozen=True)
class Advice:
    tool: str
    action: str
    snippet: str
    note: str


def detect_build_system(repo_root) -> str:
    root = Path(repo_root)
    if (root / "build.gradle.kts").exists():
        return GRADLE_KOTLIN
    if (root / "build.gradle").exists():
        return GRADLE_GROOVY
    if (root / "pom.xml").exists():
        return MAVEN
    return UNKNOWN


def advice_for(tool, repo_root, reason=ABSENT, build_system=None):
    """None means "nothing useful to say" — never a guess."""
    system = build_system or detect_build_system(repo_root)
    if system == UNKNOWN:
        return None
    snippet = _SNIPPETS.get(tool, {}).get(system)
    if snippet is None:
        return None
    note = _CLASS_FILE_NOTE if tool in _BYTECODE_TOOLS else ""
    action = "upgrade" if reason == TOO_OLD else "add"
    return Advice(tool=tool, action=action, snippet=snippet, note=note)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_complexity_probe_advisory.py -v`
Expected: PASS — 15 tests

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black scripts/complexity_probe_advisory.py tests/test_complexity_probe_advisory.py
uv run ruff check --fix scripts/complexity_probe_advisory.py tests/test_complexity_probe_advisory.py
git add scripts/complexity_probe_advisory.py tests/test_complexity_probe_advisory.py
git commit -m "feat(probe): build advice for missing tools, install vs upgrade"
```

---

### Task 7: Sinks

**Files:**
- Create: `scripts/complexity_probe_sinks.py`
- Test: `tests/test_complexity_probe_sinks.py`

**Interfaces:**
- Consumes: `Measurement`, `FunctionMetric`, `RAN`, `UNVERIFIED` (Task 1); `Thresholds`, `NO_THRESHOLDS` (Task 5)
- Produces: `TranscriptSink().render(measurement, thresholds) -> str`; `ArtifactSink().render(measurement, thresholds) -> dict`; `ReviewSink().render(measurement, thresholds) -> str`

**The rule these encode:** a threshold breach is highlighted as *a place to look*, never worded as a finding or a failure.

- [ ] **Step 1: Write the failing test**

```python
"""One measurement, three renderings. No sink may word a breach as a failure —
numbers point, they do not judge."""

import json

from complexity_probe_measurement import (
    RAN,
    UNVERIFIED,
    FunctionMetric,
    Measurement,
)
from complexity_probe_sinks import ArtifactSink, ReviewSink, TranscriptSink
from complexity_probe_thresholds import NO_THRESHOLDS, Thresholds


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_complexity_probe_sinks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'complexity_probe_sinks'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Where a measurement goes: the transcript, the audit artifact, or a review.

One producer, three consumers — the probe does not know which sink it feeds,
which is what lets the same lizard run serve the TDD cycle, the Phase 0
Measurements artifact and on-demand chunk review without any of them learning
about each other.

No sink words a breach as a failure. A threshold breach is a place to look;
the judgment belongs to a lens, not to a number.
"""

from complexity_probe_measurement import RAN


def _sorted_by_complexity(functions):
    return sorted(
        functions, key=lambda metric: metric.cyclomatic_complexity, reverse=True
    )


def _is_worth_a_look(metric, thresholds) -> bool:
    limit = thresholds.cyclomatic_complexity if thresholds else None
    return limit is not None and metric.cyclomatic_complexity > limit


class TranscriptSink:
    """For the TDD cycle: compact lines the agent must answer to."""

    def render(self, measurement, thresholds) -> str:
        if measurement.status != RAN:
            return f"{measurement.status}: {measurement.reason}"
        if not measurement.functions:
            return "measured the change: no functions touched"

        lines = [f"measured {len(measurement.functions)} changed function(s):"]
        for metric in _sorted_by_complexity(measurement.functions):
            marker = (
                "   <- worth a look"
                if _is_worth_a_look(metric, thresholds)
                else ""
            )
            lines.append(
                f"  {metric.name}  CC {metric.cyclomatic_complexity}"
                f"  {metric.length} lines{marker}"
            )
        return "\n".join(lines)


class ArtifactSink:
    """For the Phase 0 Measurements artifact — data, not prose."""

    def render(self, measurement, thresholds) -> dict:
        return {
            "status": measurement.status,
            "reason": measurement.reason,
            "skipped": list(measurement.skipped),
            "thresholds": {
                "cyclomatic_complexity": (
                    thresholds.cyclomatic_complexity if thresholds else None
                ),
                "source": thresholds.source if thresholds else "none declared",
            },
            "functions": [
                {
                    "name": metric.name,
                    "path": metric.path,
                    "start_line": metric.start_line,
                    "end_line": metric.end_line,
                    "cyclomatic_complexity": metric.cyclomatic_complexity,
                    "length": metric.length,
                    "parameter_count": metric.parameter_count,
                }
                for metric in measurement.functions
            ],
        }


class ReviewSink:
    """For on-demand chunk review: outlier first, so a lens knows where to look."""

    def render(self, measurement, thresholds) -> str:
        if measurement.status != RAN:
            return f"{measurement.status}: {measurement.reason}"
        if not measurement.functions:
            return "measured the chunk: no functions found"

        lines = [f"measured {len(measurement.functions)} function(s):"]
        for metric in _sorted_by_complexity(measurement.functions):
            marker = (
                "   <- outlier, worth a look"
                if _is_worth_a_look(metric, thresholds)
                else ""
            )
            lines.append(
                f"  {metric.name}  ({metric.path}:{metric.start_line})"
                f"  CC {metric.cyclomatic_complexity}"
                f"  nesting-proxy {metric.parameter_count}"
                f"  {metric.length} lines{marker}"
            )
        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_complexity_probe_sinks.py -v`
Expected: PASS — 11 tests

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black scripts/complexity_probe_sinks.py tests/test_complexity_probe_sinks.py
uv run ruff check --fix scripts/complexity_probe_sinks.py tests/test_complexity_probe_sinks.py
git add scripts/complexity_probe_sinks.py tests/test_complexity_probe_sinks.py
git commit -m "feat(probe): three sinks; a breach points, it never judges"
```

---

### Task 8: The CLI

**Files:**
- Create: `scripts/complexity_probe.py`
- Test: `tests/test_complexity_probe_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 1-7
- Produces: `main(argv=None) -> int`; exit code `0` for any non-blocking outcome, `1` only when the gate blocks

**CLI contract (spec §4.4):**

```
scripts/complexity_probe.py <paths>
scripts/complexity_probe.py --scope working-tree
scripts/complexity_probe.py --json
scripts/complexity_probe.py --gate        # apply the cycle-gate verdict
```

- [ ] **Step 1: Write the failing test**

```python
"""The CLI wires the parts together. Exit code 1 is reserved for a blocking
gate verdict — never for a high number."""

import json

import complexity_probe


class TestOutputModes:
    def test_default_output_is_human_readable(self, tmp_path, capsys):
        source_file = tmp_path / "sample.py"
        source_file.write_text("def add(first, second):\n    return first + second\n")
        exit_code = complexity_probe.main([str(source_file)])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "add" in captured.out

    def test_json_output_parses(self, tmp_path, capsys):
        source_file = tmp_path / "sample.py"
        source_file.write_text("def add(first, second):\n    return first + second\n")
        complexity_probe.main([str(source_file), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "ran"


class TestExitCodes:
    def test_a_high_complexity_function_still_exits_zero(self, tmp_path, capsys):
        """Numbers never fail the run — only silence does."""
        branches = "\n".join(
            f"    if value == {index}:\n        return {index}" for index in range(25)
        )
        source_file = tmp_path / "branchy.py"
        source_file.write_text(f"def classify(value):\n{branches}\n    return -1\n")
        assert complexity_probe.main([str(source_file)]) == 0

    def test_gate_mode_on_a_successful_measurement_exits_zero(self, tmp_path):
        source_file = tmp_path / "sample.py"
        source_file.write_text("def add(first, second):\n    return first + second\n")
        assert complexity_probe.main([str(source_file), "--gate"]) == 0


class TestScopeWiring:
    def test_scope_full_is_accepted(self, tmp_path, capsys):
        (tmp_path / "sample.py").write_text("def add(a_value):\n    return a_value\n")
        exit_code = complexity_probe.main(
            ["--scope", "full", "--repo-root", str(tmp_path)]
        )
        assert exit_code == 0

    def test_an_empty_working_tree_exits_zero_and_says_so(self, tmp_path, capsys):
        exit_code = complexity_probe.main(
            ["--scope", "working-tree", "--repo-root", str(tmp_path)]
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out.strip()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_complexity_probe_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'complexity_probe'`

- [ ] **Step 3: Write minimal implementation**

```python
"""The complexity probe's command line.

Composition root: the only place concrete probes, sinks and threshold sources
are chosen. Everything below this file takes its collaborators as arguments,
which is why the verdict logic is testable without a subprocess.

`--scope` shares its vocabulary with scripts/mutation_gate.py so the two
sensors are asked for a target the same way.
"""

import argparse
import json
import sys

from complexity_probe_gate import CycleGate
from complexity_probe_lizard import LizardProbe
from complexity_probe_scope import resolve_scope
from complexity_probe_sinks import ArtifactSink, ReviewSink, TranscriptSink
from complexity_probe_thresholds import discover_thresholds


def build_parser():
    parser = argparse.ArgumentParser(
        description="Measure changed functions. Numbers point; they never judge."
    )
    parser.add_argument("paths", nargs="*", help="files, directories, or a range")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--scope",
        default=None,
        help="working-tree (default), merge-base, full, a path, or path:start-end",
    )
    parser.add_argument("--json", action="store_true", help="emit the artifact payload")
    parser.add_argument(
        "--gate",
        action="store_true",
        help="apply the cycle-gate verdict; exit 1 only on silence",
    )
    parser.add_argument(
        "--sink",
        choices=("transcript", "review"),
        default="transcript",
        help="which rendering to print (ignored with --json)",
    )
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)

    if arguments.paths:
        selection = resolve_scope(
            arguments.paths[0] if len(arguments.paths) == 1 else None,
            repo_root=arguments.repo_root,
        )
        paths = (
            selection.paths if len(arguments.paths) == 1 else tuple(arguments.paths)
        )
    else:
        selection = resolve_scope(arguments.scope, repo_root=arguments.repo_root)
        paths = selection.paths

    probe = LizardProbe()
    measurement = probe.measure(paths)
    thresholds = discover_thresholds(arguments.repo_root)

    if arguments.json:
        print(json.dumps(ArtifactSink().render(measurement, thresholds), indent=2))
    else:
        sink = TranscriptSink() if arguments.sink == "transcript" else ReviewSink()
        print(sink.render(measurement, thresholds))

    if arguments.gate:
        verdict = CycleGate().evaluate(measurement, probe.is_available())
        if verdict.blocks:
            print(verdict.message, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_complexity_probe_cli.py -v`
Expected: PASS — 6 tests

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS — 850 existing + ~70 new

- [ ] **Step 6: Format, lint, commit**

```bash
uv run black scripts/ tests/
uv run ruff check --fix scripts/ tests/
git add scripts/complexity_probe.py tests/test_complexity_probe_cli.py
git commit -m "feat(probe): CLI composition root; exit 1 only on silence"
```

---

### Task 9: Wire the TDD REFACTOR step

**Files:**
- Modify: `skills/tdd/SKILL.md:156-177` (the REFACTOR section)
- Test: `tests/test_tdd_refactor_is_mechanical.py`

**Interfaces:**
- Consumes: `scripts/complexity_probe.py --scope working-tree --gate` from Task 8
- Produces: no code interface — a skill contract, guarded by a structure test

**What changes:** the checklist keeps all seven prose items (only three are mechanizable; the others are judgment and stay). What is added is the obligation to run the probe first and report its output or state why not.

- [ ] **Step 1: Write the failing test**

```python
"""The REFACTOR step must name the probe command and the say-why-or-block rule.
A structure test, matching the repo's other skill-contract tests."""

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills/tdd/SKILL.md"


def refactor_section() -> str:
    text = SKILL.read_text()
    start = text.index("#### 3. REFACTOR")
    end = text.index("####", start + 10)
    return text[start:end]


class TestTheRefactorStepIsMechanical:
    def test_it_names_the_probe_command(self):
        assert "complexity_probe.py" in refactor_section()

    def test_it_states_the_gate_rule(self):
        section = refactor_section().lower()
        assert "state why" in section or "say why" in section

    def test_it_still_says_silence_is_the_failure(self):
        assert "silence" in refactor_section().lower()

    def test_the_seven_judgment_items_survive(self):
        section = refactor_section()
        for item in (
            "Names",
            "Functions",
            "Duplication",
            "Nesting",
            "Responsibility drift",
            "Dependency direction",
            "Mocking as a design signal",
        ):
            assert item in section

    def test_it_does_not_promise_a_threshold(self):
        """The plugin ships no numbers; the step must not imply one."""
        section = refactor_section()
        assert "CC > " not in section
        assert "CC>" not in section
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tdd_refactor_is_mechanical.py -v`
Expected: FAIL — `test_it_names_the_probe_command` and `test_it_states_the_gate_rule`

- [ ] **Step 3: Edit the skill**

Replace the two opening lines of `#### 3. REFACTOR — clean up while green (mandatory)` (currently "Evaluate every cycle… Silence is how this step evaporates.") with:

```markdown
Evaluate every cycle, even when the outcome is "nothing to refactor" — say so
explicitly. Silence is how this step evaporates.

**Measure first, then judge.** Run the probe over what this cycle changed:

```bash
scripts/complexity_probe.py --scope working-tree --gate
```

It prints each changed function's complexity and length. **Produce that output,
or state why there isn't any** — no probe for this language, tool absent, needs
compiled classes. Either is a complete answer; saying nothing is not, and
`--gate` exits non-zero on it.

The numbers are triage, never a verdict: a high count says *look here*, it does
not say *fix this*. The judgment is still yours, against the checklist below.
```

Leave the seven checklist items and the escalation list unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tdd_refactor_is_mechanical.py -v`
Expected: PASS — 5 tests

- [ ] **Step 5: Commit**

```bash
git add skills/tdd/SKILL.md tests/test_tdd_refactor_is_mechanical.py
git commit -m "feat(tdd): REFACTOR measures before it judges"
```

---

### Task 10: Chunk review in /clean-code and /solid

**Files:**
- Modify: `skills/clean-code/SKILL.md` (the "Review — two gears" section)
- Modify: `skills/solid/SKILL.md` (the Invocation section)
- Test: `tests/test_chunk_review_contract.py`

**Interfaces:**
- Consumes: `scripts/complexity_probe.py --sink review` from Task 8
- Produces: no code interface — a skill contract

**Reminder from the spec:** this path **never blocks**. It prints numbers, then the lens judges what they point at.

- [ ] **Step 1: Write the failing test**

```python
"""Both chunk-review lenses must measure before judging, and neither may block."""

from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1] / "skills"
CLEAN_CODE = (SKILLS / "clean-code/SKILL.md").read_text()
SOLID = (SKILLS / "solid/SKILL.md").read_text()


class TestBothLensesMeasure:
    def test_clean_code_names_the_probe(self):
        assert "complexity_probe.py" in CLEAN_CODE

    def test_solid_names_the_probe(self):
        assert "complexity_probe.py" in SOLID

    def test_both_use_the_review_sink(self):
        assert "--sink review" in CLEAN_CODE
        assert "--sink review" in SOLID


class TestNeitherBlocksAHuman:
    def test_clean_code_says_it_never_blocks(self):
        assert "never blocks" in CLEAN_CODE.lower()

    def test_solid_says_it_never_blocks(self):
        assert "never blocks" in SOLID.lower()

    def test_neither_passes_the_gate_flag(self):
        assert "--gate" not in CLEAN_CODE
        assert "--gate" not in SOLID


class TestTheScopeFormsAreDocumented:
    def test_clean_code_documents_the_range_form(self):
        assert ":40-120" in CLEAN_CODE or "start-end" in CLEAN_CODE

    def test_solid_documents_the_range_form(self):
        assert ":40-120" in SOLID or "start-end" in SOLID
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_chunk_review_contract.py -v`
Expected: FAIL — all eight

- [ ] **Step 3: Edit `skills/clean-code/SKILL.md`**

Insert immediately before the `## Review — two gears` heading:

```markdown
## Measure before you read

Run the probe over the chunk first — it costs a second and tells you where to
look:

```bash
scripts/complexity_probe.py --sink review <scope>
```

`<scope>` is a path, a diff, or a range (`OrderService.java:40-120`); bare means
the uncommitted working tree. **This never blocks** — it prints numbers and
hands them to your judgment. A high count is a place to look, not a finding: it
is only a finding once you can name the readability or changeability cost.

Where the probe cannot run — no probe for the language, tool absent — say so and
review unaided. Absence is data, never silence (`docs/status-vocabulary.md`).
```

- [ ] **Step 4: Edit `skills/solid/SKILL.md`**

Insert immediately after the Invocation section's pre-authorization paragraph:

```markdown
**Measure before you read.** Run `scripts/complexity_probe.py --sink review <scope>`
over the target first. `<scope>` is a path, a diff, or a range
(`OrderService.java:40-120`). **This never blocks** — the numbers are triage,
pointing at where a type switch or a god class is likely to be. A finding still
has to name the design cost; a number alone is not one. Where the probe cannot
run, record it and analyze unaided (`docs/status-vocabulary.md`).
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_chunk_review_contract.py -v`
Expected: PASS — 8 tests

- [ ] **Step 6: Commit**

```bash
git add skills/clean-code/SKILL.md skills/solid/SKILL.md tests/test_chunk_review_contract.py
git commit -m "feat(lenses): chunk review measures first, never blocks"
```

---

### Task 11: Documentation and issue closure

**Files:**
- Modify: `README.md`
- Modify: `docs/status-vocabulary.md` (link the now-real implementation)
- Modify: `docs/superpowers/specs/2026-08-02-cycle-gate-verdict-design.md` (status header)
- Test: `tests/test_readme_documents_the_probe.py`

**This is the documentation duty spec §4.4 defers to implementation time**, and the repo's standing rule that README is updated whenever skills, commands, scripts or structure change.

- [ ] **Step 1: Write the failing test**

```python
"""README must document the probe now that it is invokable — the duty spec
§4.4 defers until the behavior exists."""

from pathlib import Path

README = (Path(__file__).resolve().parents[1] / "README.md").read_text()


class TestTheReadmeDocumentsTheProbe:
    def test_it_names_the_script(self):
        assert "complexity_probe.py" in README

    def test_it_shows_the_three_entry_points(self):
        assert "--gate" in README
        assert "--sink review" in README
        assert "--json" in README

    def test_it_states_the_gate_rule(self):
        assert "silence" in README.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_readme_documents_the_probe.py -v`
Expected: FAIL — all three

- [ ] **Step 3: Add a README section**

Place it alongside the existing scripts documentation:

````markdown
### Complexity probe

Measures changed functions so the cleanup step produces evidence instead of
prose. Three entry points, one engine:

```bash
# during a TDD cycle — the only mode that can block, and only on silence
scripts/complexity_probe.py --scope working-tree --gate

# reviewing a chunk you wrote by hand — never blocks
scripts/complexity_probe.py --sink review OrderService.java:40-120

# feeding an audit
scripts/complexity_probe.py --scope full --json
```

The rule: **produce a measurement, or state why there isn't one. Silence is the
only thing that blocks.** Numbers are triage — a high count is a place to look,
never a finding on its own.

Thresholds come from what your repo already declares (Checkstyle, PMD, ruff's
`mccabe`, ESLint's `complexity`). The plugin ships none of its own. Statuses
follow [`docs/status-vocabulary.md`](docs/status-vocabulary.md).
````

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_readme_documents_the_probe.py -v`
Expected: PASS — 3 tests

- [ ] **Step 5: Mark the spec implemented**

In `docs/superpowers/specs/2026-08-02-cycle-gate-verdict-design.md`, change the status line to:

```markdown
**Status: IMPLEMENTED 2026-XX-XX.** Plan:
[`../plans/2026-08-02-cycle-gate.md`](../plans/2026-08-02-cycle-gate.md).
Resolves §5.1 and §5.2 of ...
```

- [ ] **Step 6: Full suite, format, lint, commit**

```bash
uv run black . && uv run ruff check --fix . && uv run pytest -q
git add README.md docs/ tests/test_readme_documents_the_probe.py
git commit -m "docs: document the complexity probe and mark the spec implemented"
```

- [ ] **Step 7: Close the issues**

```bash
gh issue close 117 --comment "Implemented: scripts/complexity_probe_lizard.py is the measurement engine; ArtifactSink feeds Phase 0. See docs/superpowers/plans/2026-08-02-cycle-gate.md"
gh issue close 121 --comment "Absorbed: docs/status-vocabulary.md defines ran/degraded/unverified, every lens report carries Coverage & method, and the invariant is enforced at construction in complexity_probe_measurement.py"
gh issue close 124 --comment "Implemented via proposal 1 (REFACTOR calls a script). Proposal 2 (PostToolUse hook) was not needed — the diagnosed failure is silent skipping, not rationalized breaches. See the spec §1.1"
```

**#118 stays open** — the report `## Measurements` section and before→after deltas consume `ArtifactSink` but are a separate deliverable.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §2.2 verdict vocabulary | 1 (invariant), 3 (verdict) |
| §2.3 the gate rule | 3 |
| §2.4 the bricking bug | 3 (`TestTheBugThatBricksLanguages`) |
| §3 humans get feedback | 10 (`TestNeitherBlocksAHuman`) |
| §4.1 components | 1-8 |
| §4.2 thresholds | 5 |
| §4.3 chunk review | 4 (range/working-tree), 10 (wiring) |
| §4.4 invocation surface | 8 (CLI), 11 (docs) |
| §4.5 tool advisories | 6 |
| §4.6 DIP | every task — collaborators injected, verdict tested with stubs |
| §5 failure handling | 2 (unavailable/crash), 3 (no probe), 5 (absent config), 6 (advice) |
| §5.1 known inaccuracy | 2 (baseline asserts CC 6, the undercount) |
| §5.2 Java 25 verification | 2 (`TestAgainstRealLizardOnJava25`) |
| §6 testing | 1-8 stub-based; 2 real-probe fixtures; 5 threshold fixtures; 6 advisories |

**Gap found and closed:** spec §6 asks the mutation gate to cover the verdict logic. Not a task — `scripts/mutation_gate.py --scope working-tree` over `complexity_probe_gate.py` is a verification step, not a deliverable. Run it after Task 3 and kill any survivor before moving on.

**Placeholder scan:** none — every step carries runnable code or exact prose.

**Type consistency:** `Measurement(status, functions, reason, skipped)` is constructed identically in Tasks 1, 2, 3, 7. `thresholds_for(repo_root)` matches across all five sources. `render(measurement, thresholds)` matches across all three sinks. `advice_for(tool, repo_root, reason, build_system)` matches Task 6's tests. `resolve_scope(argument, repo_root, git_runner)` matches Task 4 and Task 8.

**Known risk:** Task 8's positional-path handling routes a single argument through `resolve_scope` (so a range works) but multiple arguments straight to the probe. If a reviewer finds that ambiguous, splitting `--scope` from positional paths entirely is the cleaner fix.
