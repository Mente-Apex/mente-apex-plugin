# test-quality Mutation Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/test-quality`'s hand-operated mutation gate with a real, repeatable one that runs `mutmut` (Python) and Stryker (JS/TS) over any audited codebase, plus a prose backend for documentation-as-code suites.

**Architecture:** One selector partitions a file selection by stack; one backend per stack turns its partition into a uniform `Survivor` list; the gate merges them and writes the result into the lens's report. Backends are a registry, not an if-chain — `mutmut` and Stryker mutate for themselves and are invoked-and-parsed, while only the prose backend generates mutants. Everything runs in a scratch copy so the operator's tree is never touched.

**Tech Stack:** Python 3.14 (uv), pytest, `mutmut` 3.6 (audited-repo dep), Stryker `@stryker-mutator/core` + a runner plugin (audited-repo dep, fnm-selected Node). No new runtime dependency for the plugin itself beyond `mutmut` as a dev dep.

**Spec:** `docs/superpowers/specs/2026-07-29-mutation-gate-design.md`

## Global Constraints

- Python is `uv`-managed: `uv run pytest`, `uv add --dev` — never bare `pip install`, never a hand-activated `.venv`, never system `python3`.
- Node is fnm-selected: any Stryker invocation goes through the fnm-resolved Node/`npx`, never system Node.
- `requires-python = ">=3.14"`; the repo targets `py314` under black (line-length 88) and ruff. Lint that ruff cannot autofix is a blocker.
- `black` owns formatting: run `uv run black .` before every commit; never hand-format.
- New scripts follow the existing flat-module convention in `scripts/` (`config_sync_*.py`), not a package.
- The gate never installs a tool into the audited repo; it reports the declared-install command as an opt-in.
- The operator's working tree must be byte-identical after any run, including an aborted one.
- The report is the single source of truth: survivors go into the report file, not stdout only.
- No score/percentage anywhere in operator-facing output.
- Every task ends green: `uv run pytest` passes before the commit.

---

### Task 1: `Survivor` and selection partitioning

The pure core, no subprocesses. Everything else depends on these names.

**Files:**
- Create: `scripts/mutation_gate.py`
- Test: `tests/test_mutation_gate_selection.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Survivor` dataclass (frozen): `artifact: str`, `location: str`, `mutant: str`, `associated_tests: tuple[str, ...]`, `backend: str`, `granularity: str`, `status: str = "survived"`.
  - `partition(paths: Iterable[str]) -> dict[str, tuple[str, ...]]` returning stack-keyed partitions with keys `"python"`, `"js"`, `"prose"`, `"unresolved"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mutation_gate_selection.py
"""Selection partitioning: which backend owns which file.

The gate invokes each backend once over its partition — never once per test —
so partitioning is the whole of dispatch and deserves its own tests.
"""

from mutation_gate import Survivor, partition


def test_partitions_a_mixed_selection_by_stack():
    partitions = partition(
        [
            "src/api/money.py",
            "web/src/cart.ts",
            "web/src/cart.js",
            "skills/test-quality/SKILL.md",
            "assets/logo.png",
        ]
    )

    assert partitions["python"] == ("src/api/money.py",)
    assert partitions["js"] == ("web/src/cart.ts", "web/src/cart.js")
    assert partitions["prose"] == ("skills/test-quality/SKILL.md",)
    assert partitions["unresolved"] == ("assets/logo.png",)


def test_absent_stacks_partition_to_empty_not_missing():
    partitions = partition(["only/thing.py"])

    assert partitions["js"] == ()
    assert partitions["prose"] == ()


def test_survivor_is_frozen_so_a_reporter_cannot_rewrite_a_finding():
    import dataclasses
    import pytest

    survivor = Survivor(
        artifact="src/money.py",
        location="discount",
        mutant="and -> or",
        associated_tests=("tests/test_money.py::test_member_discount",),
        backend="mutmut",
        granularity="function",
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        survivor.artifact = "elsewhere.py"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mutation_gate_selection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mutation_gate'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/mutation_gate.py
"""The /test-quality mutation gate.

"Suite still green" proves nothing when the thing you changed is the test, so
this runs real mutation testing: change the code under test mechanically and
see whether the suite notices. mutmut and Stryker do their own mutating, so a
backend's job is `survivors(selection)` — how it gets them is its business.
"""

from dataclasses import dataclass

PYTHON_SUFFIXES = (".py",)
JS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
PROSE_SUFFIXES = (".md",)


@dataclass(frozen=True)
class Survivor:
    """One mutant the suite failed to kill.

    `granularity` records what the backend could actually tell us — Stryker
    resolves a survivor to a line and the tests that covered it, mutmut only to
    the mutated function. The report states which, rather than implying a
    precision the backend never had.
    """

    artifact: str
    location: str
    mutant: str
    associated_tests: tuple[str, ...]
    backend: str
    granularity: str
    status: str = "survived"


def partition(paths):
    """Group paths by the backend that owns them.

    Dispatch is per partition, not per test: mutmut and Stryker are invoked
    over a file set, and a per-test invocation loop would be ruinously slow.
    """
    partitions = {"python": [], "js": [], "prose": [], "unresolved": []}
    for path in paths:
        if path.endswith(PYTHON_SUFFIXES):
            partitions["python"].append(path)
        elif path.endswith(JS_SUFFIXES):
            partitions["js"].append(path)
        elif path.endswith(PROSE_SUFFIXES):
            partitions["prose"].append(path)
        else:
            partitions["unresolved"].append(path)
    return {stack: tuple(paths) for stack, paths in partitions.items()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mutation_gate_selection.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black scripts/mutation_gate.py tests/test_mutation_gate_selection.py
uv run ruff check scripts/mutation_gate.py tests/test_mutation_gate_selection.py
uv run pytest
git add scripts/mutation_gate.py tests/test_mutation_gate_selection.py
git commit -m "feat(mutation-gate): Survivor shape and stack partitioning"
```

---

### Task 2: Scratch-copy isolation

Mutation writes to the tree — `mutmut` materialises `mutants/`, Stryker `.stryker-tmp/`, the prose backend edits in place. None of that may reach the operator's tree.

**Files:**
- Create: `scripts/mutation_gate_workspace.py`
- Test: `tests/test_mutation_gate_workspace.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `scratch_workspace(repo_root: Path) -> ContextManager[Path]` yielding a path to an isolated copy of the repo at HEAD; cleans up on exit, including on exception.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mutation_gate_workspace.py
"""The operator's tree is never the mutation target.

mutmut materialises a mutants/ directory and Stryker a .stryker-tmp/; the prose
backend rewrites the artifact in place. All of it happens in a scratch copy, so
a dirty tree is safe and the operator can keep working during a sweep.
"""

import subprocess

import pytest

from mutation_gate_workspace import scratch_workspace


@pytest.fixture
def git_repo(tmp_path):
    """A one-commit git repo with an uncommitted edit, i.e. a dirty tree."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "money.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    (tmp_path / "money.py").write_text("VALUE = 2\n", encoding="utf-8")
    return tmp_path


def test_yields_a_writable_copy_that_is_not_the_original(git_repo):
    with scratch_workspace(git_repo) as workspace:
        assert workspace != git_repo
        assert (workspace / "money.py").is_file()
        (workspace / "money.py").write_text("MUTATED = 0\n", encoding="utf-8")

    assert git_repo.joinpath("money.py").read_text(encoding="utf-8") == "VALUE = 2\n"


def test_an_exception_inside_still_leaves_the_original_untouched(git_repo):
    before = (git_repo / "money.py").read_bytes()

    with pytest.raises(RuntimeError):
        with scratch_workspace(git_repo) as workspace:
            (workspace / "money.py").write_text("MUTATED = 0\n", encoding="utf-8")
            raise RuntimeError("backend blew up mid-run")

    assert (git_repo / "money.py").read_bytes() == before


def test_cleans_up_after_itself(git_repo):
    with scratch_workspace(git_repo) as workspace:
        recorded = workspace

    assert not recorded.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mutation_gate_workspace.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mutation_gate_workspace'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/mutation_gate_workspace.py
"""Isolation for mutation runs.

Every backend writes: mutmut materialises mutants/, Stryker .stryker-tmp/, and
the prose backend edits the artifact in place. The operator did not ask for any
of that in their tree, and their tree may be dirty, so runs happen in a copy.

A git worktree is preferred where the repo has one commit to anchor to — it is
cheap and gives a clean checkout. A plain copy is the fallback, so the gate
works in a directory that is not a git repo at all.
"""

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


def _try_worktree(repo_root, destination):
    """Add a detached worktree at HEAD. Returns True on success."""
    result = subprocess.run(
        ["git", "worktree", "add", "--detach", "-q", str(destination), "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _remove_worktree(repo_root, destination):
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(destination)],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )


@contextmanager
def scratch_workspace(repo_root):
    """Yield an isolated copy of `repo_root` for mutating, then clean it up."""
    repo_root = Path(repo_root)
    parent = Path(tempfile.mkdtemp(prefix="mutation-gate-"))
    destination = parent / "workspace"
    used_worktree = _try_worktree(repo_root, destination)
    if not used_worktree:
        shutil.copytree(
            repo_root, destination, ignore=shutil.ignore_patterns(".git", ".venv")
        )
    try:
        yield destination
    finally:
        if used_worktree:
            _remove_worktree(repo_root, destination)
        shutil.rmtree(parent, ignore_errors=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mutation_gate_workspace.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black scripts/mutation_gate_workspace.py tests/test_mutation_gate_workspace.py
uv run ruff check scripts/mutation_gate_workspace.py tests/test_mutation_gate_workspace.py
uv run pytest
git add scripts/mutation_gate_workspace.py tests/test_mutation_gate_workspace.py
git commit -m "feat(mutation-gate): run mutations in a scratch workspace"
```

---

### Task 3: `mutmut` backend

Parses real captured output. The spike (2026-07-29) established: `mutmut` 3.6.0 runs clean on 3.14.6, its config key is `source_paths`, and it associates tests with the mutated **function** via `mutants/mutmut-stats.json` — there is no `killedBy` and no per-line mapping.

**Files:**
- Create: `scripts/mutation_gate_mutmut.py`
- Create: `tests/fixtures/mutmut-stats.json`
- Create: `tests/fixtures/mutmut-results.txt`
- Test: `tests/test_mutation_gate_mutmut.py`
- Modify: `pyproject.toml` (add `mutmut` to `[dependency-groups] dev`)

**Interfaces:**
- Consumes: `Survivor` from Task 1.
- Produces: `survivors_from_output(results_text: str, stats: dict, diffs: dict[str, str]) -> tuple[Survivor, ...]` — pure parsing, no subprocess.

- [ ] **Step 1: Create the captured fixtures**

```json
// tests/fixtures/mutmut-stats.json — captured verbatim from a real mutmut 3.6.0 run
{
  "tests_by_mangled_function_name": {
    "money.x_discount": [
      "tests/test_money.py::test_member_over_threshold_gets_ten_percent_off",
      "tests/test_money.py::test_vacuous_guard_asserts_nothing_real"
    ]
  },
  "duration_by_test": {
    "tests/test_money.py::test_member_over_threshold_gets_ten_percent_off": 0.000176,
    "tests/test_money.py::test_vacuous_guard_asserts_nothing_real": 0.000121
  },
  "stats_time": 0.0797
}
```

```text
# tests/fixtures/mutmut-results.txt — captured verbatim from `mutmut results`
    money.x_discount__mutmut_1: survived
    money.x_discount__mutmut_2: survived
    money.x_discount__mutmut_3: killed
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_mutation_gate_mutmut.py
"""Parsing real mutmut 3.6.0 output.

Pinned against output captured verbatim from a live run, so a schema change in
mutmut fails loudly here instead of silently reporting no survivors — the worst
possible failure for a tool whose whole job is to report survivors.
"""

import json
from pathlib import Path

from mutation_gate_mutmut import survivors_from_output

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixtures():
    stats = json.loads((FIXTURES / "mutmut-stats.json").read_text(encoding="utf-8"))
    results = (FIXTURES / "mutmut-results.txt").read_text(encoding="utf-8")
    return results, stats


def test_reports_only_the_survivors_not_the_killed_mutants():
    results, stats = load_fixtures()

    survivors = survivors_from_output(results, stats, diffs={})

    assert [s.mutant for s in survivors] == [
        "money.x_discount__mutmut_1",
        "money.x_discount__mutmut_2",
    ]


def test_associates_each_survivor_with_the_tests_that_exercise_its_function():
    results, stats = load_fixtures()

    survivors = survivors_from_output(results, stats, diffs={})

    assert survivors[0].associated_tests == (
        "tests/test_money.py::test_member_over_threshold_gets_ten_percent_off",
        "tests/test_money.py::test_vacuous_guard_asserts_nothing_real",
    )


def test_declares_function_granularity_because_mutmut_has_no_line_mapping():
    results, stats = load_fixtures()

    survivors = survivors_from_output(results, stats, diffs={})

    assert survivors[0].granularity == "function"
    assert survivors[0].location == "money.x_discount"
    assert survivors[0].backend == "mutmut"


def test_carries_the_diff_when_mutmut_show_supplied_one():
    results, stats = load_fixtures()
    diff = "-    if is_member and total > 100:\n+    if is_member or total > 100:"

    survivors = survivors_from_output(
        results, stats, diffs={"money.x_discount__mutmut_1": diff}
    )

    assert diff in survivors[0].mutant_diff


def test_an_unmapped_function_yields_no_tests_rather_than_an_exception():
    results = "    ghost.x_vanished__mutmut_1: survived\n"

    survivors = survivors_from_output(results, {}, diffs={})

    assert survivors[0].associated_tests == ()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_mutation_gate_mutmut.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mutation_gate_mutmut'`

- [ ] **Step 4: Add `mutant_diff` to `Survivor`**

In `scripts/mutation_gate.py`, add the field to the dataclass (after `granularity`, before `status`):

```python
    mutant_diff: str = ""
```

- [ ] **Step 5: Write minimal implementation**

```python
# scripts/mutation_gate_mutmut.py
"""The Python backend: invoke mutmut, parse what it gives back.

Spike 2026-07-29, mutmut 3.6.0 on 3.14.6. Two things shape this module:

1. The config key is `source_paths`; `paths_to_mutate` deprecation-warns.
2. Association is function-level. `mutants/mutmut-stats.json` maps a mutated
   function to the pytest node ids that exercise it — there is no killedBy and
   no per-line mapping, unlike Stryker. So a survivor reads as "a mutant in
   discount() survived; these tests exercise it", which is still enough to name
   a vacuous guard.
"""

import re

from mutation_gate import Survivor

RESULT_LINE = re.compile(r"^\s*(?P<mutant>\S+):\s*(?P<status>\w+)\s*$", re.MULTILINE)
MUTANT_SUFFIX = re.compile(r"__mutmut_\d+$")


def _function_of(mutant_name):
    """`money.x_discount__mutmut_1` -> `money.x_discount`."""
    return MUTANT_SUFFIX.sub("", mutant_name)


def survivors_from_output(results_text, stats, diffs):
    """Turn `mutmut results` + mutmut-stats.json into Survivors."""
    tests_by_function = stats.get("tests_by_mangled_function_name", {})
    survivors = []
    for match in RESULT_LINE.finditer(results_text):
        if match.group("status") != "survived":
            continue
        mutant = match.group("mutant")
        function = _function_of(mutant)
        survivors.append(
            Survivor(
                artifact=function.split(".")[0],
                location=function,
                mutant=mutant,
                mutant_diff=diffs.get(mutant, ""),
                associated_tests=tuple(tests_by_function.get(function, ())),
                backend="mutmut",
                granularity="function",
            )
        )
    return tuple(survivors)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_mutation_gate_mutmut.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Declare the dependency**

```bash
uv add --dev mutmut
uv run mutmut --version
```

Expected: `mutmut, version 3.6.0` or later. Confirm `uv.lock` changed.

- [ ] **Step 8: Format, lint, commit**

```bash
uv run black scripts/ tests/
uv run ruff check scripts/ tests/
uv run pytest
git add scripts/mutation_gate.py scripts/mutation_gate_mutmut.py tests/ pyproject.toml uv.lock
git commit -m "feat(mutation-gate): mutmut backend, pinned to captured 3.6.0 output"
```

---

### Task 4: Stryker backend

The spike established Stryker's JSON report is the integration surface: per-mutant `killedBy`, `coveredBy`, and a line/column `location`, with `testFiles[].tests[]` resolving ids to names. `coverageAnalysis: "perTest"` is what produces `coveredBy` at all.

**Files:**
- Create: `scripts/mutation_gate_stryker.py`
- Create: `tests/fixtures/stryker-mutation.json`
- Test: `tests/test_mutation_gate_stryker.py`

**Interfaces:**
- Consumes: `Survivor` from Task 1.
- Produces:
  - `survivors_from_report(report: dict) -> tuple[Survivor, ...]`
  - `default_config(mutate_globs: Sequence[str], test_runner: str) -> dict` — the generated `stryker.conf.json` body.

- [ ] **Step 1: Create the captured fixture**

```json
// tests/fixtures/stryker-mutation.json — captured from a real Stryker + vitest run
{
  "schemaVersion": "1.0",
  "files": {
    "src/money.js": {
      "language": "javascript",
      "mutants": [
        {
          "id": "1",
          "mutatorName": "ConditionalExpression",
          "replacement": "true",
          "status": "Survived",
          "static": false,
          "testsCompleted": 2,
          "coveredBy": ["0", "1"],
          "location": {
            "start": { "line": 2, "column": 7 },
            "end": { "line": 2, "column": 30 }
          }
        },
        {
          "id": "0",
          "mutatorName": "BlockStatement",
          "replacement": "{}",
          "status": "Killed",
          "static": false,
          "testsCompleted": 1,
          "killedBy": ["0"],
          "coveredBy": ["0", "1"],
          "location": {
            "start": { "line": 1, "column": 43 },
            "end": { "line": 6, "column": 2 }
          }
        },
        {
          "id": "2",
          "mutatorName": "ArithmeticOperator",
          "replacement": "total / 0.9",
          "status": "Timeout",
          "static": false,
          "coveredBy": ["0"],
          "location": {
            "start": { "line": 3, "column": 12 },
            "end": { "line": 3, "column": 24 }
          }
        }
      ]
    }
  },
  "testFiles": {
    "test/money.test.js": {
      "tests": [
        { "id": "0", "name": "member over threshold gets ten percent off" },
        { "id": "1", "name": "vacuous guard asserts nothing real" }
      ]
    }
  }
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_mutation_gate_stryker.py
"""Parsing a real Stryker JSON report (schemaVersion 1.0).

Stryker is the richer of the two backends — it resolves a survivor to a line,
a column, and the ids of the tests that covered it. This module is where that
precision is turned into the same Survivor shape mutmut produces, so the report
never asks an operator to reconcile two tools' output.
"""

import json
from pathlib import Path

from mutation_gate_stryker import default_config, survivors_from_report

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_report():
    return json.loads(
        (FIXTURES / "stryker-mutation.json").read_text(encoding="utf-8")
    )


def test_reports_survivors_and_ignores_killed_mutants():
    survivors = survivors_from_report(load_report())

    assert [s.mutant for s in survivors if s.status == "survived"] == [
        "ConditionalExpression -> true"
    ]


def test_resolves_covering_test_ids_to_names():
    survivors = survivors_from_report(load_report())
    survived = next(s for s in survivors if s.status == "survived")

    assert survived.associated_tests == (
        "member over threshold gets ten percent off",
        "vacuous guard asserts nothing real",
    )


def test_declares_line_granularity_and_a_precise_location():
    survivors = survivors_from_report(load_report())
    survived = next(s for s in survivors if s.status == "survived")

    assert survived.granularity == "line"
    assert survived.location == "src/money.js:2:7"
    assert survived.backend == "stryker"


def test_a_timeout_is_inconclusive_not_a_pass():
    survivors = survivors_from_report(load_report())

    timed_out = [s for s in survivors if s.status == "timeout"]
    assert len(timed_out) == 1
    assert timed_out[0].location == "src/money.js:3:12"


def test_generated_config_requests_per_test_coverage():
    config = default_config(mutate_globs=["src/**/*.js"], test_runner="vitest")

    assert config["coverageAnalysis"] == "perTest"
    assert config["testRunner"] == "vitest"
    assert config["mutate"] == ["src/**/*.js"]
    assert "json" in config["reporters"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_mutation_gate_stryker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mutation_gate_stryker'`

- [ ] **Step 4: Write minimal implementation**

```python
# scripts/mutation_gate_stryker.py
"""The JS/TS backend: read Stryker's JSON report.

Spike 2026-07-29, @stryker-mutator/core + vitest-runner on Node 24.18.0 (fnm).
The report at reports/mutation/mutation.json carries, per mutant, a status, a
mutatorName, a replacement, killedBy, coveredBy, and a line/column location;
testFiles[].tests[] resolves those ids to names.

`coverageAnalysis: "perTest"` is what produces coveredBy at all, so a generated
config that omits it yields a report with no test association — which would
silently disable the survivor policy. Hence default_config pins it.
"""

from mutation_gate import Survivor

STATUS_MAP = {"Survived": "survived", "Timeout": "timeout", "NoCoverage": "no_coverage"}


def _test_names(report):
    """Map Stryker's test ids to human names, across all test files."""
    names = {}
    for test_file in report.get("testFiles", {}).values():
        for test in test_file.get("tests", []):
            names[test["id"]] = test["name"]
    return names


def default_config(mutate_globs, test_runner):
    """The stryker.conf.json body offered to a repo that has none."""
    return {
        "testRunner": test_runner,
        "mutate": list(mutate_globs),
        "reporters": ["json", "clear-text"],
        "coverageAnalysis": "perTest",
    }


def survivors_from_report(report):
    """Turn a Stryker JSON report into Survivors.

    Timeouts come through as their own status rather than being dropped: a
    mutant that hung is neither killed nor survived, and counting it either way
    is a lie the operator cannot see.
    """
    names = _test_names(report)
    survivors = []
    for path, file_report in report.get("files", {}).items():
        for mutant in file_report.get("mutants", []):
            status = STATUS_MAP.get(mutant.get("status"))
            if status is None:
                continue
            start = mutant.get("location", {}).get("start", {})
            survivors.append(
                Survivor(
                    artifact=path,
                    location=f"{path}:{start.get('line')}:{start.get('column')}",
                    mutant=f"{mutant['mutatorName']} -> {mutant['replacement']}",
                    associated_tests=tuple(
                        names[test_id]
                        for test_id in mutant.get("coveredBy", ())
                        if test_id in names
                    ),
                    backend="stryker",
                    granularity="line",
                    status=status,
                )
            )
    return tuple(survivors)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_mutation_gate_stryker.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Format, lint, commit**

```bash
uv run black scripts/ tests/
uv run ruff check scripts/ tests/
uv run pytest
git add scripts/mutation_gate_stryker.py tests/
git commit -m "feat(mutation-gate): Stryker backend, pinned to a captured JSON report"
```

---

### Task 5: The `covers` marker and prose backend

For suites whose subject is a document. The marker is prose-only and optional — code-shaped tests need no annotation.

**Files:**
- Create: `scripts/mutation_gate_prose.py`
- Test: `tests/test_mutation_gate_prose.py`
- Modify: `pyproject.toml` (register the `covers` marker)
- Modify: `tests/conftest.py` (add the `covered_slice` helper fixture)

**Interfaces:**
- Consumes: `Survivor` from Task 1.
- Produces:
  - `extract_section(text: str, heading_text: str) -> str`
  - `mutate(text: str, heading_text: str, operator: str) -> str` for operators `"delete"`, `"blank"`, `"invert"`
  - `covered_slice(request, repo_root)` pytest fixture returning the declared slice's text

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mutation_gate_prose.py
"""The prose backend's three mutation operators.

Where mutmut and Stryker derive a mutant-to-test mapping from coverage, prose
has none, so the test declares its target with @pytest.mark.covers and the
harness mutates exactly that slice. Windowing the wrong region is precisely the
bug class this replaces.
"""

import pytest

from mutation_gate_prose import extract_section, mutate

DOC = """# Title

Intro text.

## Step 2

The loop MUST run per component.
Do NOT skip a component.

## Step 3

Later content mentioning per component too.
"""


def test_extract_section_stops_at_the_next_same_level_heading():
    section = extract_section(DOC, "Step 2")

    assert "MUST run per component" in section
    assert "Later content" not in section


def test_delete_operator_removes_only_the_declared_slice():
    mutated = mutate(DOC, "Step 2", operator="delete")

    assert "MUST run per component" not in mutated
    assert "Later content mentioning per component too." in mutated


def test_blank_operator_keeps_the_heading_and_drops_the_body():
    mutated = mutate(DOC, "Step 2", operator="blank")

    assert "## Step 2" in mutated
    assert "MUST run per component" not in mutated


def test_invert_operator_flips_directive_polarity_inside_the_slice_only():
    mutated = mutate(DOC, "Step 2", operator="invert")

    assert "MUST NOT run per component" in mutated
    assert "Do skip a component." in mutated
    assert "Later content mentioning per component too." in mutated


def test_an_unknown_heading_is_an_error_not_a_silent_no_op():
    with pytest.raises(ValueError, match="Nonexistent"):
        mutate(DOC, "Nonexistent", operator="delete")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mutation_gate_prose.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mutation_gate_prose'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/mutation_gate_prose.py
"""The prose backend, for suites whose subject is a document.

Without it a documentation-as-code repo gets no gate at all — neither mutmut nor
Stryker will mutate a Markdown heading. Unlike them, this backend generates and
applies its own mutants, over exactly the slice the test declared.

The three operators answer three different questions:
  delete — does the test notice the section is gone at all?
  blank  — does it need the CONTENT, or only the heading?
  invert — does it check what the directive SAYS, or only that a word appears?
"""

import re

INVERSIONS = (
    ("MUST NOT", "MUST"),
    ("MUST", "MUST NOT"),
    ("Do NOT", "Do"),
    ("never", "always"),
    ("always", "never"),
)


def _locate(text, heading_text):
    """Return (heading_start, body_start, body_end) for the declared section."""
    heading_pattern = re.compile(
        r"^(#{1,6})\s.*" + re.escape(heading_text) + r".*$", re.MULTILINE
    )
    heading_match = heading_pattern.search(text)
    if heading_match is None:
        raise ValueError(f"heading containing {heading_text!r} not found")
    level = len(heading_match.group(1))
    body_start = heading_match.end()
    next_heading = re.compile(r"^#{1," + str(level) + r"}\s", re.MULTILINE).search(
        text, body_start
    )
    body_end = next_heading.start() if next_heading else len(text)
    return heading_match.start(), body_start, body_end


def extract_section(text, heading_text):
    """The text between a heading and the next same-or-higher-level heading."""
    _, body_start, body_end = _locate(text, heading_text)
    return text[body_start:body_end]


def _invert(body):
    """Flip directive polarity once per occurrence, longest token first."""
    pattern = re.compile("|".join(re.escape(word) for word, _ in INVERSIONS))
    replacements = dict(INVERSIONS)
    return pattern.sub(lambda m: replacements[m.group(0)], body)


def mutate(text, heading_text, operator):
    """Return `text` with the declared slice mutated by `operator`."""
    heading_start, body_start, body_end = _locate(text, heading_text)
    if operator == "delete":
        return text[:heading_start] + text[body_end:]
    if operator == "blank":
        return text[:body_start] + "\n\n(section body removed)\n\n" + text[body_end:]
    if operator == "invert":
        return text[:body_start] + _invert(text[body_start:body_end]) + text[body_end:]
    raise ValueError(f"unknown operator: {operator!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mutation_gate_prose.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Register the marker and add the fixture**

In `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
markers = [
    "covers(artifact, section): the artifact slice this prose guard verifies; the mutation gate mutates exactly this slice",
]
```

In `tests/conftest.py`, append:

```python
@pytest.fixture
def covered_slice(request):
    """The artifact slice this test declared via @pytest.mark.covers.

    The marker is also what the test READS, so the declaration and the
    assertion cannot drift apart — a guard can no longer window a region other
    than the one it named, which is the bug class the mutation gate exists to
    stop from recurring.
    """
    marker = request.node.get_closest_marker("covers")
    assert marker is not None, "this fixture requires an @pytest.mark.covers marker"
    artifact = Path(__file__).resolve().parents[1] / marker.args[0]
    text = artifact.read_text(encoding="utf-8")
    section = marker.kwargs.get("section")
    if section is None:
        return text
    return mutation_gate_prose.extract_section(text, section)
```

Add the imports `tests/conftest.py` needs at the top, beside the existing ones:

```python
import mutation_gate_prose  # noqa: E402
```

- [ ] **Step 6: Write the marker's own guard test**

```python
# append to tests/test_mutation_gate_prose.py


@pytest.mark.covers(
    "skills/test-quality/SKILL.md", section="Applying is guarded by two gates"
)
def test_the_marker_delivers_the_declared_slice_and_nothing_else(covered_slice):
    assert "mutation gate" in covered_slice
    assert "## Guardrails" not in covered_slice
```

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS, no unknown-marker warnings.

- [ ] **Step 8: Write the failing test for the marker-driven runner**

```python
# append to tests/test_mutation_gate_prose.py


def test_a_guard_that_survives_every_operator_is_reported_as_a_survivor(tmp_path):
    from mutation_gate_prose import prose_survivors

    artifact = tmp_path / "doc.md"
    artifact.write_text(DOC, encoding="utf-8")
    declarations = [("tests/test_doc.py::test_vacuous", "doc.md", "Step 2")]

    survivors = prose_survivors(
        tmp_path, declarations, run_test=lambda node_id: True  # always green
    )

    assert survivors[0].associated_tests == ("tests/test_doc.py::test_vacuous",)
    assert survivors[0].granularity == "section"
    assert {s.mutant for s in survivors} == {"delete", "blank", "invert"}


def test_a_guard_killed_by_the_delete_operator_is_not_reported_for_it(tmp_path):
    from mutation_gate_prose import prose_survivors

    artifact = tmp_path / "doc.md"
    artifact.write_text(DOC, encoding="utf-8")
    declarations = [("tests/test_doc.py::test_sound", "doc.md", "Step 2")]

    def run_test(node_id):
        # Green only while the section body is still present.
        return "MUST run per component" in artifact.read_text(encoding="utf-8")

    survivors = prose_survivors(tmp_path, declarations, run_test=run_test)

    assert "delete" not in {s.mutant for s in survivors}


def test_the_artifact_is_byte_identical_even_when_the_runner_raises(tmp_path):
    from mutation_gate_prose import prose_survivors

    artifact = tmp_path / "doc.md"
    artifact.write_text(DOC, encoding="utf-8")
    before = artifact.read_bytes()

    def exploding_runner(node_id):
        raise RuntimeError("pytest died mid-mutant")

    with pytest.raises(RuntimeError):
        prose_survivors(
            tmp_path,
            [("tests/test_doc.py::test_x", "doc.md", "Step 2")],
            run_test=exploding_runner,
        )

    assert artifact.read_bytes() == before
```

- [ ] **Step 9: Run test to verify it fails**

Run: `uv run pytest tests/test_mutation_gate_prose.py -v`
Expected: FAIL with `ImportError: cannot import name 'prose_survivors'`

- [ ] **Step 10: Implement the runner**

Append to `scripts/mutation_gate_prose.py`:

```python
from pathlib import Path

from mutation_gate import Survivor

OPERATORS = ("delete", "blank", "invert")


def prose_survivors(repo_root, declarations, run_test):
    """Apply each operator to each declared slice; report what stayed green.

    `declarations` is (test_node_id, artifact_path, section) triples, collected
    from @pytest.mark.covers. `run_test` returns True when the test still
    passes — a True under a mutant means the guard did not notice, which is the
    definition of vacuous.

    Restore is try/finally over the original text held in memory, never a git
    operation: the harness must be safe on a dirty tree, and a checkout would
    eat unrelated work.
    """
    survivors = []
    for node_id, artifact_path, section in declarations:
        artifact = Path(repo_root) / artifact_path
        original = artifact.read_text(encoding="utf-8")
        for operator in OPERATORS:
            try:
                artifact.write_text(
                    mutate(original, section, operator=operator), encoding="utf-8"
                )
                still_green = run_test(node_id)
            finally:
                artifact.write_text(original, encoding="utf-8")
            if still_green:
                survivors.append(
                    Survivor(
                        artifact=artifact_path,
                        location=f"{artifact_path} § {section}",
                        mutant=operator,
                        associated_tests=(node_id,),
                        backend="prose",
                        granularity="section",
                        # Presence-only guards legitimately survive inversion,
                        # so that operator reports at a lower tier.
                        status="survived" if operator != "invert" else "survived_minor",
                    )
                )
    return tuple(survivors)


def collect_declarations(repo_root):
    """Read @pytest.mark.covers declarations out of the suite.

    `pytest --collect-only -q` plus the marker's own arguments; a test with no
    marker yields nothing, which is what makes it "unverifiable by construction"
    rather than a failure.
    """
    import json
    import subprocess

    result = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            "--collect-only",
            "-q",
            "--covers-manifest=-",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ()
    return tuple(tuple(entry) for entry in json.loads(result.stdout or "[]"))
```

Add the `--covers-manifest` hook to `tests/conftest.py` so collection can emit the declarations:

```python
def pytest_addoption(parser):
    parser.addoption(
        "--covers-manifest",
        default=None,
        help="Write collected @pytest.mark.covers declarations as JSON and exit.",
    )


def pytest_collection_finish(session):
    """Emit (node_id, artifact, section) for every guard that declared one."""
    destination = session.config.getoption("--covers-manifest")
    if destination is None:
        return
    declarations = []
    for item in session.items:
        marker = item.get_closest_marker("covers")
        if marker is None:
            continue
        declarations.append(
            [item.nodeid, marker.args[0], marker.kwargs.get("section")]
        )
    payload = json.dumps(declarations)
    if destination == "-":
        print(payload)
    else:
        Path(destination).write_text(payload, encoding="utf-8")
```

with `import json` and `from pathlib import Path` at the top of `tests/conftest.py`.

- [ ] **Step 11: Run test to verify it passes**

Run: `uv run pytest tests/test_mutation_gate_prose.py -v`
Expected: PASS (9 tests)

- [ ] **Step 12: Format, lint, commit**

```bash
uv run black scripts/ tests/
uv run ruff check scripts/ tests/
uv run pytest
git add scripts/mutation_gate_prose.py tests/ pyproject.toml
git commit -m "feat(mutation-gate): covers marker, prose operators, and the slice runner"
```

---

### Task 6: Backend registry, tool detection, and provisioning advice

The strategy seam. A fourth backend must be additive — no if-chain.

**Files:**
- Modify: `scripts/mutation_gate.py`
- Test: `tests/test_mutation_gate_dispatch.py`

**Interfaces:**
- Consumes: `partition` and `Survivor` from Task 1.
- Produces:
  - `Backend` protocol: `stack: str`, `tool: str`, `available(repo_root) -> bool`, `install_hint(repo_root) -> str`, `survivors(repo_root, paths) -> tuple[Survivor, ...]`
  - `run_gate(repo_root, paths, backends) -> GateResult`
  - `GateResult`: `survivors: tuple[Survivor, ...]`, `unavailable: tuple[tuple[str, str], ...]` (stack, install hint), `unresolved: tuple[str, ...]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mutation_gate_dispatch.py
"""Dispatch across a mixed codebase, with fakes standing in for the tools.

Fakes, not real runs: a Python API with a TypeScript frontend is the normal
shape this lens audits, and the suite must prove both backends select and merge
without requiring mutmut or Stryker to be installed on the machine running it.
"""

from mutation_gate import GateResult, Survivor, run_gate


class FakeBackend:
    """Stands in for mutmut or Stryker; records what it was asked to mutate."""

    def __init__(self, stack, tool, available=True, survivors=()):
        self.stack = stack
        self.tool = tool
        self._available = available
        self._survivors = survivors
        self.called_with = None

    def available(self, repo_root):
        return self._available

    def install_hint(self, repo_root):
        return f"install {self.tool}"

    def survivors(self, repo_root, paths):
        self.called_with = tuple(paths)
        return self._survivors


def survivor(backend):
    return Survivor(
        artifact="a",
        location="a:1",
        mutant="m",
        associated_tests=("t",),
        backend=backend,
        granularity="line",
    )


def test_a_mixed_repo_runs_both_backends_once_each_and_merges_the_results(tmp_path):
    python = FakeBackend("python", "mutmut", survivors=(survivor("mutmut"),))
    js = FakeBackend("js", "stryker", survivors=(survivor("stryker"),))

    result = run_gate(tmp_path, ["api/money.py", "web/cart.ts"], [python, js])

    assert python.called_with == ("api/money.py",)
    assert js.called_with == ("web/cart.ts",)
    assert {s.backend for s in result.survivors} == {"mutmut", "stryker"}


def test_a_backend_with_an_empty_partition_is_never_invoked(tmp_path):
    js = FakeBackend("js", "stryker")

    run_gate(tmp_path, ["api/money.py"], [FakeBackend("python", "mutmut"), js])

    assert js.called_with is None


def test_a_present_stack_with_an_absent_tool_reports_a_hint_and_continues(tmp_path):
    python = FakeBackend("python", "mutmut", available=False)
    js = FakeBackend("js", "stryker", survivors=(survivor("stryker"),))

    result = run_gate(tmp_path, ["api/money.py", "web/cart.ts"], [python, js])

    assert result.unavailable == (("python", "install mutmut"),)
    assert len(result.survivors) == 1


def test_files_no_backend_claims_are_reported_as_unresolved(tmp_path):
    result = run_gate(tmp_path, ["assets/logo.png"], [FakeBackend("python", "mutmut")])

    assert result.unresolved == ("assets/logo.png",)


def test_the_result_carries_no_score_anywhere(tmp_path):
    result = run_gate(tmp_path, ["api/money.py"], [FakeBackend("python", "mutmut")])

    assert not hasattr(result, "score")
    assert isinstance(result, GateResult)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mutation_gate_dispatch.py -v`
Expected: FAIL with `ImportError: cannot import name 'GateResult'`

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/mutation_gate.py`:

```python
@dataclass(frozen=True)
class GateResult:
    """What one gate run produced.

    No score field, deliberately. A percentage gets gamed and tells an operator
    nothing; the survivors and their associated tests are the whole signal.
    """

    survivors: tuple
    unavailable: tuple
    unresolved: tuple


def run_gate(repo_root, paths, backends):
    """Partition the selection, invoke each backend once, merge the results.

    A backend whose partition is empty is never invoked — a repo with no JS is
    simply a run where the Stryker partition is empty, not a failure. A backend
    whose tool is missing yields an install hint and the run continues: the gate
    never installs anything on the operator's behalf, and a missing tool
    degrades a run rather than failing it.
    """
    partitions = partition(paths)
    survivors = []
    unavailable = []
    for backend in backends:
        selection = partitions.get(backend.stack, ())
        if not selection:
            continue
        if not backend.available(repo_root):
            unavailable.append((backend.stack, backend.install_hint(repo_root)))
            continue
        survivors.extend(backend.survivors(repo_root, selection))
    return GateResult(
        survivors=tuple(survivors),
        unavailable=tuple(unavailable),
        unresolved=partitions.get("unresolved", ()),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mutation_gate_dispatch.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black scripts/ tests/
uv run ruff check scripts/ tests/
uv run pytest
git add scripts/mutation_gate.py tests/test_mutation_gate_dispatch.py
git commit -m "feat(mutation-gate): backend registry with graceful tool absence"
```

---

### Task 7: CLI entry point and scope resolution

Default scope is the merge-base diff, so a sweep is stable across intermediate commits.

**Files:**
- Modify: `scripts/mutation_gate.py`
- Test: `tests/test_mutation_gate_scope.py`

**Interfaces:**
- Consumes: `run_gate` from Task 6, `scratch_workspace` from Task 2.
- Produces: `changed_paths(repo_root, scope) -> tuple[str, ...]` for scope in `"merge-base"`, `"working-tree"`, `"full"`; and `main(argv) -> int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mutation_gate_scope.py
"""What the gate mutates by default.

Merge-base rather than working-tree, so a sweep does not change its answer as
the operator makes intermediate commits mid-audit. Full-repo mutation is far
too slow for an interactive skill, so it stays behind an explicit flag.
"""

import pytest

from mutation_gate import changed_paths


def test_merge_base_is_the_default_scope():
    import inspect

    signature = inspect.signature(changed_paths)
    assert signature.parameters["scope"].default == "merge-base"


def test_merge_base_scope_diffs_against_the_fork_point(git_repo_with_branch):
    repo, _ = git_repo_with_branch

    paths = changed_paths(repo, scope="merge-base")

    assert paths == ("feature.py",)


def test_working_tree_scope_sees_uncommitted_edits(git_repo_with_branch):
    repo, _ = git_repo_with_branch
    (repo / "scratch.py").write_text("x = 1\n", encoding="utf-8")

    paths = changed_paths(repo, scope="working-tree")

    assert "scratch.py" in paths


def test_an_unknown_scope_is_rejected(git_repo_with_branch):
    repo, _ = git_repo_with_branch

    with pytest.raises(ValueError, match="unknown scope"):
        changed_paths(repo, scope="everything-ever")
```

Add this fixture to `tests/conftest.py`:

```python
@pytest.fixture
def git_repo_with_branch(tmp_path):
    """A repo on a feature branch one commit ahead of its default branch."""
    run = lambda *args: subprocess.run(args, cwd=tmp_path, check=True, capture_output=True)
    run("git", "init", "-q", "-b", "main")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "T")
    (tmp_path / "base.py").write_text("BASE = 1\n", encoding="utf-8")
    run("git", "add", ".")
    run("git", "commit", "-qm", "base")
    run("git", "checkout", "-qb", "feature")
    (tmp_path / "feature.py").write_text("FEATURE = 1\n", encoding="utf-8")
    run("git", "add", ".")
    run("git", "commit", "-qm", "feature")
    return tmp_path, "main"
```

and `import subprocess` at the top of `tests/conftest.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mutation_gate_scope.py -v`
Expected: FAIL with `ImportError: cannot import name 'changed_paths'`

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/mutation_gate.py` (and add `import argparse`, `import json`, `import subprocess`, `import sys` at the top):

```python
def _git(repo_root, *args):
    result = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=True
    )
    return result.stdout


def _default_branch(repo_root):
    """The local default branch, preferring main, falling back to master."""
    branches = _git(repo_root, "branch", "--format=%(refname:short)").split()
    for candidate in ("main", "master"):
        if candidate in branches:
            return candidate
    return branches[0] if branches else "HEAD"


def changed_paths(repo_root, scope="merge-base"):
    """The files this run mutates.

    merge-base is the default because it is stable: an operator committing
    mid-audit should not change what the sweep covers. Full-repo mutation is
    far too slow to be anyone's default in an interactive skill.
    """
    if scope == "merge-base":
        base = _default_branch(repo_root)
        fork_point = _git(repo_root, "merge-base", base, "HEAD").strip()
        output = _git(repo_root, "diff", "--name-only", fork_point, "HEAD")
    elif scope == "working-tree":
        output = _git(repo_root, "status", "--porcelain", "--untracked-files=all")
        output = "\n".join(line[3:] for line in output.splitlines())
    elif scope == "full":
        output = _git(repo_root, "ls-files")
    else:
        raise ValueError(f"unknown scope: {scope!r}")
    return tuple(line for line in output.splitlines() if line)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mutation_gate_scope.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Add the CLI**

Append to `scripts/mutation_gate.py`:

```python
def main(argv=None):
    """Run the gate and print the result as JSON for the calling agent."""
    parser = argparse.ArgumentParser(description="Run the test-quality mutation gate.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--scope", choices=("merge-base", "working-tree", "full"), default="merge-base"
    )
    arguments = parser.parse_args(argv)

    paths = changed_paths(arguments.repo_root, scope=arguments.scope)
    with scratch_workspace(arguments.repo_root) as workspace:
        result = run_gate(workspace, paths, default_backends())
    print(json.dumps(as_report_payload(result, scope=arguments.scope), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`default_backends()` and `as_report_payload()` live in `scripts/mutation_gate_report.py`, built in Task 8. Import them **inside** `main` rather than at module top:

```python
    from mutation_gate_report import as_report_payload, default_backends
```

The deferred import is deliberate and not laziness — `mutation_gate_report` imports the three backend modules, which import `mutation_gate` for `Survivor`. A top-level import here would close that cycle. Task 11's `/solid` pass will look at this; the local import is the intended answer, and `run_gate` still depends only on the `Backend` protocol.

Until Task 8 lands, `main` is not exercised by tests. Verify it by hand at the end of Task 8:

```bash
uv run python scripts/mutation_gate.py --repo-root . --scope working-tree
```

- [ ] **Step 6: Format, lint, commit**

```bash
uv run black scripts/ tests/
uv run ruff check scripts/ tests/
uv run pytest
git add scripts/mutation_gate.py tests/
git commit -m "feat(mutation-gate): merge-base scope resolution and CLI"
```

---

### Task 8: Report rendering and the report-template section

Survivors land in the report, not stdout — this lens holds the report is the single source of truth.

**Files:**
- Create: `scripts/mutation_gate_report.py`
- Modify: `skills/test-quality/references/report-template.md`
- Test: `tests/test_mutation_gate_report.py`

**Interfaces:**
- Consumes: `GateResult` from Task 6.
- Produces:
  - `as_report_payload(result, scope) -> dict`
  - `render_markdown(result, scope) -> str`
  - `default_backends() -> tuple[Backend, ...]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mutation_gate_report.py
"""Rendering survivors into the report.

Two rules the lens cannot bend: never a percentage, and never silence about an
inconclusive result. A timed-out mutant reported as nothing reads to an operator
exactly like a clean run, which is the failure this whole gate exists to stop.
"""

from mutation_gate import GateResult, Survivor
from mutation_gate_report import render_markdown


def result_with(*survivors, unavailable=(), unresolved=()):
    return GateResult(
        survivors=tuple(survivors), unavailable=unavailable, unresolved=unresolved
    )


SURVIVED = Survivor(
    artifact="src/money.py",
    location="money.x_discount",
    mutant="money.x_discount__mutmut_1",
    mutant_diff="-    if is_member and total > 100:\n+    if is_member or total > 100:",
    associated_tests=("tests/test_money.py::test_member_discount",),
    backend="mutmut",
    granularity="function",
)

TIMED_OUT = Survivor(
    artifact="src/money.js",
    location="src/money.js:3:12",
    mutant="ArithmeticOperator -> total / 0.9",
    associated_tests=("member over threshold gets ten percent off",),
    backend="stryker",
    granularity="line",
    status="timeout",
)


def test_names_the_test_and_the_mutant_not_a_score():
    markdown = render_markdown(result_with(SURVIVED), scope="merge-base")

    assert "tests/test_money.py::test_member_discount" in markdown
    assert "money.x_discount__mutmut_1" in markdown
    assert "%" not in markdown


def test_states_the_granularity_each_backend_supplied():
    markdown = render_markdown(result_with(SURVIVED), scope="merge-base")

    assert "function" in markdown
    assert "mutmut" in markdown


def test_a_timeout_is_rendered_as_inconclusive_not_as_a_survivor():
    markdown = render_markdown(result_with(TIMED_OUT), scope="merge-base")

    assert "Inconclusive" in markdown
    assert "src/money.js:3:12" in markdown


def test_an_unavailable_tool_is_stated_with_its_install_command():
    markdown = render_markdown(
        result_with(unavailable=(("js", "npm install -D @stryker-mutator/core"),)),
        scope="merge-base",
    )

    assert "not available" in markdown
    assert "npm install -D @stryker-mutator/core" in markdown


def test_the_scope_that_produced_the_result_is_recorded():
    markdown = render_markdown(result_with(SURVIVED), scope="full")

    assert "full" in markdown


def test_a_clean_run_says_so_rather_than_rendering_an_empty_section():
    markdown = render_markdown(result_with(), scope="merge-base")

    assert "No survivors" in markdown
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mutation_gate_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mutation_gate_report'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/mutation_gate_report.py
"""Rendering a GateResult into the lens's report.

Never a percentage: "87%" tells an operator nothing actionable, and a threshold
gets gamed. What they need is "this mutant survived and these tests should have
killed it".

Inconclusive results get their own section rather than being folded into either
column, because a timed-out mutant reported as silence reads exactly like a
clean run.
"""

from mutation_gate_mutmut import MutmutBackend
from mutation_gate_stryker import StrykerBackend
from mutation_gate_prose import ProseBackend


def default_backends():
    """The backends a normal run dispatches over."""
    return (MutmutBackend(), StrykerBackend(), ProseBackend())


def as_report_payload(result, scope):
    """A JSON-serialisable view for the calling agent."""
    return {
        "scope": scope,
        "survivors": [
            {
                "artifact": s.artifact,
                "location": s.location,
                "mutant": s.mutant,
                "diff": s.mutant_diff,
                "associated_tests": list(s.associated_tests),
                "backend": s.backend,
                "granularity": s.granularity,
            }
            for s in result.survivors
            if s.status == "survived"
        ],
        "inconclusive": [
            {"location": s.location, "mutant": s.mutant, "reason": s.status}
            for s in result.survivors
            if s.status != "survived"
        ],
        "unavailable": [
            {"stack": stack, "install": hint} for stack, hint in result.unavailable
        ],
        "unresolved": list(result.unresolved),
    }


def render_markdown(result, scope):
    """The Mutation-gate section body for the report."""
    lines = [f"**Scope:** {scope}", ""]

    survived = [s for s in result.survivors if s.status == "survived"]
    if survived:
        lines.append("**Survivors** — a mutant these tests failed to kill:")
        lines.append("")
        for survivor in survived:
            lines.append(
                f"- `{survivor.location}` — {survivor.mutant} "
                f"(via {survivor.backend}, {survivor.granularity} granularity)"
            )
            for test in survivor.associated_tests:
                lines.append(f"  - should have killed it: `{test}`")
            if survivor.mutant_diff:
                lines.append("")
                lines.append("    ```diff")
                for diff_line in survivor.mutant_diff.splitlines():
                    lines.append(f"    {diff_line}")
                lines.append("    ```")
        lines.append("")
    else:
        lines.append("No survivors in scope.")
        lines.append("")

    inconclusive = [s for s in result.survivors if s.status != "survived"]
    if inconclusive:
        lines.append("**Inconclusive** — neither killed nor survived:")
        lines.append("")
        for survivor in inconclusive:
            lines.append(f"- `{survivor.location}` — {survivor.mutant} ({survivor.status})")
        lines.append("")

    if result.unavailable:
        lines.append("**Backends not available:**")
        lines.append("")
        for stack, hint in result.unavailable:
            lines.append(f"- {stack}: tool not available — declare it with `{hint}`")
        lines.append("")

    if result.unresolved:
        lines.append("**Not verifiable** — no backend claims these:")
        lines.append("")
        for path in result.unresolved:
            lines.append(f"- `{path}`")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Add the three backend classes**

Each wraps its parser from Tasks 3–5 with `stack`, `tool`, `available()`, `install_hint()`, and `survivors()`. Append to the matching module. For `scripts/mutation_gate_mutmut.py`:

```python
import json
import shutil
import subprocess
from pathlib import Path


class MutmutBackend:
    """Invokes mutmut in the scratch workspace and parses what it emits."""

    stack = "python"
    tool = "mutmut"

    def available(self, repo_root):
        return shutil.which("mutmut") is not None

    def install_hint(self, repo_root):
        return "uv add --dev mutmut"

    def survivors(self, repo_root, paths):
        subprocess.run(
            ["mutmut", "run"], cwd=repo_root, capture_output=True, text=True
        )
        results = subprocess.run(
            ["mutmut", "results"], cwd=repo_root, capture_output=True, text=True
        ).stdout
        stats_path = Path(repo_root) / "mutants" / "mutmut-stats.json"
        stats = (
            json.loads(stats_path.read_text(encoding="utf-8"))
            if stats_path.is_file()
            else {}
        )
        return survivors_from_output(results, stats, diffs={})
```

For `scripts/mutation_gate_stryker.py`:

```python
import json
import shutil
import subprocess
from pathlib import Path


class StrykerBackend:
    """Invokes Stryker under the fnm-selected Node and reads its JSON report."""

    stack = "js"
    tool = "stryker"

    def available(self, repo_root):
        return (Path(repo_root) / "node_modules" / "@stryker-mutator").is_dir()

    def install_hint(self, repo_root):
        return (
            "npm install -D @stryker-mutator/core @stryker-mutator/vitest-runner"
            " (under the fnm-selected Node)"
        )

    def survivors(self, repo_root, paths):
        subprocess.run(
            ["npx", "stryker", "run"], cwd=repo_root, capture_output=True, text=True
        )
        report_path = Path(repo_root) / "reports" / "mutation" / "mutation.json"
        if not report_path.is_file():
            return ()
        return survivors_from_report(
            json.loads(report_path.read_text(encoding="utf-8"))
        )
```

For `scripts/mutation_gate_prose.py`:

```python
class ProseBackend:
    """Always available — the mutators ship with the plugin."""

    stack = "prose"
    tool = "built-in"

    def available(self, repo_root):
        return True

    def install_hint(self, repo_root):
        return ""

    def survivors(self, repo_root, paths):
        """Mutate every declared slice whose artifact is in this partition."""
        declarations = [
            declaration
            for declaration in collect_declarations(repo_root)
            if declaration[1] in set(paths)
        ]
        return prose_survivors(repo_root, declarations, run_test=_pytest_still_green)


def _pytest_still_green(node_id):
    """True when the single declared test still passes under the mutant."""
    import subprocess

    result = subprocess.run(
        ["uv", "run", "pytest", node_id, "-q"], capture_output=True, text=True
    )
    return result.returncode == 0
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_mutation_gate_report.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Add the report-template section**

In `skills/test-quality/references/report-template.md`, add before the Apply-log section:

```markdown
## Mutation gate

Written by `scripts/mutation_gate.py`. Records the scope that produced this
result, every survivor with the tests that should have killed it, and anything
inconclusive or unverifiable. Never a score — a percentage is gameable and tells
a reader nothing they can act on.

<!-- mutation-gate:begin -->
_Not yet run._
<!-- mutation-gate:end -->
```

- [ ] **Step 7: Pin the template section with a structure guard**

```python
# append to tests/test_mutation_gate_report.py
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.covers(
    "skills/test-quality/references/report-template.md", section="Mutation gate"
)
def test_the_template_carries_the_markers_the_gate_writes_between(covered_slice):
    assert "<!-- mutation-gate:begin -->" in covered_slice
    assert "<!-- mutation-gate:end -->" in covered_slice
    assert "Never a score" in covered_slice
```

- [ ] **Step 8: Format, lint, commit**

```bash
uv run black scripts/ tests/
uv run ruff check scripts/ tests/
uv run pytest
git add scripts/ tests/ skills/test-quality/references/report-template.md
git commit -m "feat(mutation-gate): report rendering and the report-template section"
```

---

### Task 9: Wire the skill — SKILL.md, analyzer, implementer

The prose changes that make the gate reachable. This is what the operator actually experiences.

**Files:**
- Modify: `skills/test-quality/SKILL.md:74-89`
- Modify: `skills/test-quality/agents/analyzer.md`
- Modify: `skills/test-quality/agents/implementer.md:11-17`
- Test: `tests/test_test_quality_skill_structure.py`

**Interfaces:**
- Consumes: the CLI from Task 7.
- Produces: no code interface; the skill's contract with its agents.

- [ ] **Step 1: Write the failing structure guard**

```python
# tests/test_test_quality_skill_structure.py
"""Structural guards for the test-quality skill's mutation-gate wiring.

Authored prose, not runtime code. Every guard declares the slice it verifies via
@pytest.mark.covers, so the mutation gate can check these guards are not
themselves vacuous — the failure mode that motivated the whole feature.
"""

import pytest


@pytest.mark.covers(
    "skills/test-quality/SKILL.md", section="Applying is guarded by two gates"
)
def test_gate_a_names_the_script_rather_than_a_manual_procedure(covered_slice):
    assert "scripts/mutation_gate.py" in covered_slice
    assert "manual" in covered_slice.lower()


@pytest.mark.covers("skills/test-quality/agents/analyzer.md", section="Mutation sweep")
def test_the_analyzer_sweeps_the_diff_and_stays_read_only(covered_slice):
    assert "merge-base" in covered_slice
    assert "scratch" in covered_slice.lower()
    assert "read-only" in covered_slice.lower()


@pytest.mark.covers("skills/test-quality/agents/analyzer.md", section="Mutation sweep")
def test_the_analyzer_files_survivors_as_rubric_eleven_findings(covered_slice):
    assert "rubric 11" in covered_slice.lower() or "rubric-11" in covered_slice.lower()
    assert "unverifiable by construction" in covered_slice


@pytest.mark.covers("skills/test-quality/agents/implementer.md", section="Gate A")
def test_gate_a_keeps_the_manual_loop_as_the_documented_fallback(covered_slice):
    assert "scripts/mutation_gate.py" in covered_slice
    assert "fallback" in covered_slice.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_test_quality_skill_structure.py -v`
Expected: FAIL — `ValueError: heading containing 'Mutation sweep' not found`

- [ ] **Step 3: Add the analyzer's sweep section**

Append to `skills/test-quality/agents/analyzer.md`:

```markdown
## Mutation sweep

Before drafting findings, run the mutation gate over the audit scope:

    uv run python scripts/mutation_gate.py --repo-root <path> --scope merge-base

Default scope is the **merge-base** diff, so the sweep does not change its answer
as the operator commits mid-audit; `--scope full` exists and is slow enough that
it is never the default. The run happens in a **scratch** workspace, so this stays
**read-only** with respect to the operator's tree — mutation writes files, and
none of them may land in the tree they are working in.

Turn the JSON it prints into findings:

- A survivor whose `associated_tests` include a test in scope → a **rubric 11**
  tending finding, "vacuous test": the mutant survived, and these tests should
  have killed it. Quote the mutant and the test; never a score.
- A prose guard with no `@pytest.mark.covers` marker → **Minor**,
  "unverifiable by construction" — the gate cannot check a guard that does not
  declare what it guards.
- An `inconclusive` entry (timeout, or a test that failed on the clean baseline)
  → report it as inconclusive with the test named. Never let it read as a pass.
- An `unavailable` entry → state the stack and the declared-install command the
  payload carries. Do not install anything; the audit continues without it.

You run the gate; you do not act on it. Every survivor still goes to the reviewer
for verification against the real test, like any other finding.
```

- [ ] **Step 4: Rewrite Gate A in the implementer**

Replace `skills/test-quality/agents/implementer.md:11-17` with:

```markdown
## Gate A — refactoring a test (rename, split, merge, restructure, de-mock)

Dispatch through the TDD refactor engine as usual, then run the **mutation gate**
over the refactored test:

    uv run python scripts/mutation_gate.py --repo-root . --scope working-tree

If the test under audit appears in a survivor's `associated_tests`, the refactor
hollowed it out — a mutant it should have killed is still alive. Revert the
refactor and report it. Record the gate result in the safety clause of the
apply-log line, quoting the mutant.

The manual loop — break the code under test by hand, confirm the test fails,
restore — remains the documented **fallback** for anything the gate cannot reach:
a repo with no mutation tool declared, an unsupported language, or a guard with
no marker. The automated gate is the sweep; the manual one is the spot check.
```

- [ ] **Step 5: Update SKILL.md's Gate A bullet**

In `skills/test-quality/SKILL.md`, replace the Gate A bullet (line 80-83) with:

```markdown
- **Refactor a test** (rename, split, merge, restructure, de-mock) → the TDD refactor
  engine **plus the mutation gate** (`scripts/mutation_gate.py`): mutate the code under
  test mechanically and confirm the refactored test *fails*. Proves the test still catches
  its bug, not just that it still passes. The manual break-and-restore loop stays as the
  fallback where no mutation tool is available.
```

And add to the Flow section, after step 2:

```markdown
   The analyzer also runs the **mutation sweep** over the diff — this is what
   catches *born-vacuous* tests, which no post-refactor gate would ever reach.
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_test_quality_skill_structure.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Verify the guards are not themselves vacuous**

For each of the four guards, delete the section it declares from a scratch copy and confirm the guard fails:

```bash
cp skills/test-quality/agents/analyzer.md /tmp/analyzer.bak
uv run python -c "
import sys; sys.path.insert(0, 'scripts')
from pathlib import Path
import mutation_gate_prose as p
path = Path('skills/test-quality/agents/analyzer.md')
path.write_text(p.mutate(path.read_text(), 'Mutation sweep', operator='delete'))
"
uv run pytest tests/test_test_quality_skill_structure.py -q
# Expected: the two analyzer guards FAIL
cp /tmp/analyzer.bak skills/test-quality/agents/analyzer.md
uv run pytest tests/test_test_quality_skill_structure.py -q
# Expected: PASS
```

Paste both runs into the task report.

- [ ] **Step 8: Format, lint, commit**

```bash
uv run black tests/
uv run ruff check tests/
uv run pytest
git add skills/test-quality/ tests/test_test_quality_skill_structure.py
git commit -m "feat(test-quality): wire the analyzer sweep and Gate A to the mutation gate"
```

---

### Task 10: Clean-run baseline (the flaky-test guard)

The spec requires it and nothing above implements it: a test that fails intermittently produces phantom kills, so a mutant "killed" by a test that was already red proves nothing.

**Files:**
- Modify: `scripts/mutation_gate.py`
- Test: `tests/test_mutation_gate_baseline.py`

**Interfaces:**
- Consumes: `run_gate`, `GateResult` from Task 6.
- Produces: `baseline(repo_root, run_suite) -> tuple[str, ...]` returning node ids already failing before any mutant; `run_gate` gains a `baseline_failures` keyword and `GateResult` a `baseline_failures` field.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mutation_gate_baseline.py
"""Tests that were already red before any mutant was applied.

A test failing intermittently produces phantom kills: the mutant looks caught,
but the test would have failed anyway. Recording the clean baseline is what
separates "this mutant was killed" from "this test is broken".
"""

from mutation_gate import Survivor, run_gate


class FakeBackend:
    stack = "python"
    tool = "mutmut"

    def __init__(self, survivors=()):
        self._survivors = survivors

    def available(self, repo_root):
        return True

    def install_hint(self, repo_root):
        return "uv add --dev mutmut"

    def survivors(self, repo_root, paths):
        return self._survivors


def test_a_baseline_failure_is_carried_into_the_result(tmp_path):
    result = run_gate(
        tmp_path,
        ["a.py"],
        [FakeBackend()],
        baseline_failures=("tests/test_a.py::test_flaky",),
    )

    assert result.baseline_failures == ("tests/test_a.py::test_flaky",)


def test_a_survivor_whose_only_test_was_already_red_is_marked_inconclusive(tmp_path):
    survivor = Survivor(
        artifact="a.py",
        location="a.py:1",
        mutant="x -> y",
        associated_tests=("tests/test_a.py::test_flaky",),
        backend="mutmut",
        granularity="line",
    )

    result = run_gate(
        tmp_path,
        ["a.py"],
        [FakeBackend(survivors=(survivor,))],
        baseline_failures=("tests/test_a.py::test_flaky",),
    )

    assert result.survivors[0].status == "unreliable_baseline"


def test_a_clean_baseline_leaves_survivors_alone(tmp_path):
    survivor = Survivor(
        artifact="a.py",
        location="a.py:1",
        mutant="x -> y",
        associated_tests=("tests/test_a.py::test_sound",),
        backend="mutmut",
        granularity="line",
    )

    result = run_gate(tmp_path, ["a.py"], [FakeBackend(survivors=(survivor,))])

    assert result.survivors[0].status == "survived"
    assert result.baseline_failures == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mutation_gate_baseline.py -v`
Expected: FAIL with `TypeError: run_gate() got an unexpected keyword argument 'baseline_failures'`

- [ ] **Step 3: Write minimal implementation**

In `scripts/mutation_gate.py`, add the field to `GateResult`:

```python
    baseline_failures: tuple = ()
```

and change `run_gate`'s signature and tail:

```python
def run_gate(repo_root, paths, backends, baseline_failures=()):
    ...
    already_red = set(baseline_failures)
    marked = tuple(
        replace(survivor, status="unreliable_baseline")
        if survivor.associated_tests
        and all(test in already_red for test in survivor.associated_tests)
        else survivor
        for survivor in survivors
    )
    return GateResult(
        survivors=marked,
        unavailable=tuple(unavailable),
        unresolved=partitions.get("unresolved", ()),
        baseline_failures=tuple(baseline_failures),
    )
```

with `from dataclasses import dataclass, replace` at the top.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mutation_gate_baseline.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Render it**

In `scripts/mutation_gate_report.py`, `unreliable_baseline` is already non-`"survived"`, so it lands in the Inconclusive section. Add the reason explicitly:

```python
    if result.baseline_failures:
        lines.append("**Unreliable baseline** — these tests were already failing:")
        lines.append("")
        for node_id in result.baseline_failures:
            lines.append(f"- `{node_id}`")
        lines.append("")
```

and a guard for it:

```python
# append to tests/test_mutation_gate_report.py
def test_baseline_failures_are_stated_not_swallowed():
    markdown = render_markdown(
        GateResult(
            survivors=(),
            unavailable=(),
            unresolved=(),
            baseline_failures=("tests/test_a.py::test_flaky",),
        ),
        scope="merge-base",
    )

    assert "already failing" in markdown
    assert "tests/test_a.py::test_flaky" in markdown
```

- [ ] **Step 6: Format, lint, commit**

```bash
uv run black scripts/ tests/
uv run ruff check scripts/ tests/
uv run pytest
git add scripts/ tests/
git commit -m "feat(mutation-gate): clean-run baseline so flaky tests cannot fake a kill"
```

---

### Task 11: `/solid` pass on the gate modules

Required by the spec. The backend dispatch is exactly the seam that hurts as an if-chain.

**Files:**
- Review: `scripts/mutation_gate.py`, `scripts/mutation_gate_workspace.py`, `scripts/mutation_gate_mutmut.py`, `scripts/mutation_gate_stryker.py`, `scripts/mutation_gate_prose.py`, `scripts/mutation_gate_report.py`

- [ ] **Step 1: Run the lens**

```
/solid scripts/mutation_gate*.py
```

Let the analyzer and reviewer both run; do not skip to the report.

- [ ] **Step 2: Read the report and decide per finding**

Expect scrutiny on: whether `run_gate` depends on the `Backend` abstraction rather than concrete classes (DIP); whether `mutation_gate.py` has taken on partitioning *and* scope resolution *and* the CLI (SRP); whether adding a fourth backend requires editing existing modules (OCP).

- [ ] **Step 3: Apply approved findings one at a time**

Each through the TDD refactor engine, full suite green after each, one commit per finding.

- [ ] **Step 4: Confirm the suite is green and paste evidence**

```bash
uv run pytest -q
```

Paste the report summary and the final run into the task report.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(mutation-gate): apply /solid findings"
```

---

### Task 12: `/skill-creator` evals on the changed skill

Required by the spec. The trigger surface shifted, so the description and agent contracts need evals, not just edits.

**Files:**
- Review: `skills/test-quality/SKILL.md`, `skills/test-quality/agents/analyzer.md`, `skills/test-quality/agents/implementer.md`

- [ ] **Step 1: Run the evals**

```
/skill-creator evaluate skills/test-quality
```

- [ ] **Step 2: Check triggering did not regress**

The description gained no new trigger phrases in this work, but the skill's *behaviour* did. Confirm the evals still route "our test suite is a mess", "are these good tests?", and "dead or redundant tests" to this lens, and that nothing now mis-routes generic "run mutation testing" requests away from it.

- [ ] **Step 3: Apply description or contract fixes the evals surface**

One at a time, re-running the evals after each.

- [ ] **Step 4: Paste the eval output into the task report and commit**

```bash
uv run pytest -q
git add skills/test-quality/
git commit -m "docs(test-quality): apply skill-creator eval findings"
```

---

### Task 13: Self-audit and close the issue

- [ ] **Step 1: Run the gate on this repo**

```bash
uv run python scripts/mutation_gate.py --repo-root . --scope merge-base
```

- [ ] **Step 2: Confirm the tree is untouched**

```bash
git status --porcelain
```

Expected: no `mutants/`, no `.stryker-tmp/`, no modified skill files.

- [ ] **Step 3: Triage what it found**

Any survivor on this branch's own tests is a real finding — fix the test, do not weaken the gate. Any *unverifiable* prose guard is expected and stays a finding, not a backfill.

- [ ] **Step 4: Record the outcome on the issue**

```bash
gh issue comment 113 --body "<what the gate found on its own repo, and what was fixed>"
```

- [ ] **Step 5: Final commit**

```bash
uv run black .
uv run ruff check .
uv run pytest
git add -A
git commit -m "test(mutation-gate): self-audit findings"
```

---

## Notes for the implementer

- **The spike is done; do not redo it.** `mutmut` 3.6.0 runs on 3.14.6, uses `source_paths`, writes `mutants/`, and gives function-level test association with no `killedBy`. Stryker gives `killedBy`/`coveredBy`/line-column via `reports/mutation/mutation.json` and needs `coverageAnalysis: "perTest"`. Both facts are already encoded in the fixtures.
- **Never widen the survivor policy into a score.** Several tests assert `"%" not in markdown`; that is deliberate, not incidental.
- **The prose backend is an adapter, not the point.** If a decision helps prose at the cost of the code path, it is the wrong decision.
- **Out of scope** (do not drift into these): backfilling `covers` markers across the existing suite, Gate B coverage-non-regression, CI wiring, any change to `config_sync*` behaviour.
