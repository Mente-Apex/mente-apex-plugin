"""The /test-quality mutation gate.

"Suite still green" proves nothing when the thing you changed is the test, so
this runs real mutation testing: change the code under test mechanically and
see whether the suite notices. mutmut and Stryker do their own mutating, so a
backend's job is `survivors(selection)` — how it gets them is its business.
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, replace
from typing import Protocol, runtime_checkable

from mutation_gate_scope import changed_paths
from mutation_gate_workspace import scratch_workspace

STACK_SUFFIXES = {
    "python": (".py",),
    "js": (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"),
    "prose": (".md",),
}


@dataclass(frozen=True)
class Survivor:
    """One mutant the suite failed to kill.

    `granularity` records what the backend could actually tell us — Stryker
    resolves a survivor to a line and the tests that covered it, mutmut only to
    the mutated function. The report states which, rather than implying a
    precision the backend never had.

    `status` is a CLOSED vocabulary. Every value the backends emit today:

    - `survived` — the mutant lived and the finding is real. mutmut emits only
      this (it drops every non-survived line); the prose backend emits it for
      every operator except `invert`; Stryker maps `Survived` to it.
    - `survived_minor` — prose only, and only for the `invert` operator:
      presence-only guards legitimately survive inversion, so that operator
      reports at a lower tier.
    - `unreliable_baseline` — assigned by `run_gate`, not by a backend, when
      every test covering the survivor was already red before any mutant ran.
    - `timeout`, `no_coverage`, `compile_error`, `runtime_error`, `ignored`,
      `pending` — Stryker's `STATUS_MAP`. A status Stryker emits that the map
      does not know raises rather than being dropped.

    Use `is_survivor()` to classify — never compare `status` by hand, or the
    vocabulary drifts out of sync across the consumers again.

    KNOWN OPEN DEFECT (not the intended contract, deliberately not fixed here):
    `survived_minor` is NOT in `SURVIVED_STATUSES`, so a real lower-tier prose
    survivor renders under "Inconclusive — neither killed nor survived" while
    the headline says "No survivors in scope", and `as_report_payload` drops its
    artifact, associated_tests and diff. It is a genuine survivor being reported
    as a non-result. Escalated as a bug in its own right; changing it is a
    behaviour change, not a refactor.
    """

    artifact: str
    location: str
    mutant: str
    associated_tests: tuple[str, ...]
    backend: str
    granularity: str
    mutant_diff: str = ""
    status: str = "survived"


# Deliberately just {"survived"} — see the KNOWN OPEN DEFECT note above.
SURVIVED_STATUSES = frozenset({"survived"})


def is_survivor(survivor):
    """True when this mutant survived outright, as opposed to inconclusive."""
    return survivor.status in SURVIVED_STATUSES


def partition(paths):
    """Group paths by the backend that owns them.

    Dispatch is per partition, not per test: mutmut and Stryker are invoked
    over a file set, and a per-test invocation loop would be ruinously slow.

    `STACK_SUFFIXES` is the single extension point: a new stack is one entry
    in that table, not a new branch here.
    """
    partitions = {stack: [] for stack in STACK_SUFFIXES}
    partitions["unresolved"] = []
    for path in paths:
        for stack, suffixes in STACK_SUFFIXES.items():
            if path.endswith(suffixes):
                partitions[stack].append(path)
                break
        else:
            partitions["unresolved"].append(path)
    return {stack: tuple(found) for stack, found in partitions.items()}


# The stacks a backend may legitimately claim. "unresolved" is not one of
# them: it is partition()'s catch-all for suffixes no stack owns, never a
# stack a backend registers against.
REGISTRABLE_STACKS = tuple(STACK_SUFFIXES)


@runtime_checkable
class Backend(Protocol):
    """A mutation-testing tool for one stack, behind a uniform seam.

    mutmut and Stryker (and any future backend) implement this without
    inheriting from it — `run_gate` only ever calls through the protocol, so
    adding a fourth backend is registering an object, not editing a dispatch
    chain.
    """

    stack: str
    tool: str

    def available(self, repo_root) -> bool: ...

    def install_hint(self, repo_root) -> str: ...

    def survivors(self, repo_root, paths) -> tuple:  # tuple[Survivor, ...]
        ...


@dataclass(frozen=True)
class GateResult:
    """What one gate run produced.

    No score field, deliberately. A percentage gets gamed and tells an operator
    nothing; the survivors and their associated tests are the whole signal.

    `unresolved` and `unclaimed` are deliberately separate: `unresolved` is a
    file whose suffix matches no stack at all, `unclaimed` is a file that DID
    land in a known stack partition (python/js/prose) for which no backend was
    registered this run. Conflating them would hide a missing backend behind
    the same label as an image asset — every input path must be accounted for
    in exactly one of survivors / unavailable / unresolved / unclaimed.

    `baseline_error` is deliberately distinct from an empty `baseline_failures`.
    Both render as "nothing to report" unless kept apart: empty means the
    baseline ran and found nothing already red, `baseline_error` means the
    baseline run itself never completed (a collection error, an internal
    pytest crash) and every `survived`/`unreliable_baseline` split below it is
    unverified, not clean. Collapsing that distinction is the one silent
    failure mode this dataclass exists to close.
    """

    survivors: tuple[Survivor, ...]
    unavailable: tuple[tuple[str, str], ...]
    unresolved: tuple[str, ...]
    unclaimed: tuple[str, ...]
    baseline_failures: tuple[str, ...] = ()
    baseline_error: str = ""


def run_gate(
    repo_root,
    paths,
    backends: list,
    baseline_failures: tuple = (),
    baseline_error: str = "",
) -> GateResult:
    """Partition the selection, invoke each backend once, merge the results.

    A backend whose partition is empty is never invoked — a repo with no JS is
    simply a run where the Stryker partition is empty, not a failure. A backend
    whose tool is missing yields an install hint and the run continues: the gate
    never installs anything on the operator's behalf, and a missing tool
    degrades a run rather than failing it.

    Two failure modes are misconfiguration, not run-time degradation, and are
    raised eagerly instead of silently tolerated: a backend declaring a stack
    `partition()` never produces (the gate misunderstanding its own data), and
    two backends registered for the same stack (an undefined, silently-merged
    outcome otherwise).

    `baseline_failures` is the set of test node ids that were already red
    before any mutant was applied (see `baseline`). A survivor covered ONLY by
    tests that were already broken proves nothing -- it is marked
    `unreliable_baseline` rather than `survived`, because a test that never
    passes cannot have been vacuous about this mutant specifically. A survivor
    covered by a mix of already-red and clean tests keeps its `survived`
    status: at least one clean, working test had a real chance to catch this
    mutant and did not, which is exactly the signal this gate exists to
    report -- silencing it just because one of several covering tests happens
    to be flaky would be the same silence-is-the-enemy failure this field
    exists to prevent. A survivor with no associated tests at all is
    unaffected either way (nothing in `baseline_failures` bears on code no
    test covers) and stays `survived`.
    """
    backends_by_stack = {}
    for backend in backends:
        if backend.stack not in REGISTRABLE_STACKS:
            raise ValueError(
                f"backend {backend.tool!r} declares stack {backend.stack!r}, "
                f"which partition() never produces "
                f"(known stacks: {REGISTRABLE_STACKS})"
            )
        if backend.stack in backends_by_stack:
            raise ValueError(
                f"two backends registered for stack {backend.stack!r}: "
                f"{backends_by_stack[backend.stack].tool!r} and {backend.tool!r}"
            )
        backends_by_stack[backend.stack] = backend

    partitions = partition(paths)
    survivors = []
    unavailable = []
    unclaimed = []
    for stack in REGISTRABLE_STACKS:
        selection = partitions.get(stack, ())
        if not selection:
            continue
        backend = backends_by_stack.get(stack)
        if backend is None:
            unclaimed.extend(selection)
            continue
        if not backend.available(repo_root):
            unavailable.append((stack, backend.install_hint(repo_root)))
            continue
        survivors.extend(backend.survivors(repo_root, selection))

    already_red = set(baseline_failures)
    marked = tuple(
        (
            replace(survivor, status="unreliable_baseline")
            if survivor.associated_tests
            and all(test in already_red for test in survivor.associated_tests)
            else survivor
        )
        for survivor in survivors
    )
    return GateResult(
        survivors=marked,
        unavailable=tuple(unavailable),
        unresolved=partitions.get("unresolved", ()),
        unclaimed=tuple(unclaimed),
        baseline_failures=tuple(baseline_failures),
        baseline_error=baseline_error,
    )


class BaselineRunFailedError(RuntimeError):
    """A `run_suite` implementation could not complete the baseline run.

    Distinct from the run completing and reporting zero or more failures: a
    missing tool or an empty selection still yields an honest, if partial,
    answer, but a baseline that never ran yields no data at all. Raising this
    rather than returning something `_failed_node_ids` would parse as "no
    failures" is what lets a caller tell "the baseline was clean" apart from
    "the baseline never ran" instead of quietly conflating the two.
    """


def baseline(repo_root, run_suite):
    """Node ids already failing before any mutant is applied.

    A test that fails intermittently produces a phantom kill: the mutant looks
    caught because the covering test went red, but the test would have failed
    anyway with no mutation in sight. Running the real suite once, with
    nothing mutated, and recording exactly what it reports as failed is what
    lets `run_gate` tell a genuine survivor apart from one whose only covering
    tests were already broken.

    `run_suite` is injected rather than this function invoking pytest itself,
    so callers can substitute a fake in tests without shelling out, and so a
    future non-pytest suite runner is a different `run_suite`, not a rewrite
    of this function. `run_suite` may raise `BaselineRunFailedError` when the
    baseline run itself did not complete; this function does not catch it --
    that decision belongs to the caller (see `_record_baseline`), which is
    what decides how a broken baseline is represented in the result.
    """
    return _failed_node_ids(run_suite(repo_root))


def _record_baseline(repo_root, run_suite):
    """Run the baseline, turning a run that never completed into an explicit,
    reportable error instead of an empty (and misleadingly clean-looking)
    baseline.

    Returns `(baseline_failures, baseline_error)`. Exactly one carries
    information when something went wrong: `baseline_error` names why the
    baseline run itself did not complete, and `baseline_failures` is left
    empty rather than guessed at -- there is no data to report a failure
    list from when the run that would have produced it never finished.
    """
    try:
        return baseline(repo_root, run_suite), ""
    except BaselineRunFailedError as exc:
        return (), str(exc)


_FAILED_PREFIX = "FAILED "


def _failed_node_ids(output):
    """Parse pytest's `-rf` short summary into the node ids that failed.

    `-rf` prints one `FAILED <node id>[ - <reason>]` line per failing test in
    the short summary section regardless of verbosity elsewhere in the run,
    which is far more reliable to parse than scraping full tracebacks out of
    `-v` output.
    """
    node_ids = []
    for line in output.splitlines():
        if not line.startswith(_FAILED_PREFIX):
            continue
        remainder = line[len(_FAILED_PREFIX) :]
        node_ids.append(remainder.split(" - ", 1)[0].strip())
    return tuple(node_ids)


def _pytest_run_suite(repo_root):
    """The real suite, run once, with no mutation applied.

    `uv run pytest` because this repo's Python toolchain is uv-managed --
    never a bare `pytest` or a system interpreter, which could resolve to an
    environment missing dependencies the suite needs and misreport half the
    suite as failing.

    A non-{0,1} exit code (anything but "all passed" or "some tests failed")
    means the run itself broke -- a collection error, an internal pytest
    crash -- rather than reporting a normal pass/fail outcome.
    `_failed_node_ids` would silently read that as an empty, all-clean
    baseline. A warning alone is not enough here: nothing in the rendered
    report captures Python warnings, so an operator reading only the markdown
    or JSON output would see every survivor at face value with no baseline
    having actually run. Raising `BaselineRunFailedError` instead forces the
    failure through `_record_baseline` into `GateResult.baseline_error`,
    where it reaches the operator-facing report.
    """
    result = subprocess.run(
        ["uv", "run", "pytest", "--tb=no", "-q", "-rf"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise BaselineRunFailedError(
            f"uv run pytest exited {result.returncode} in {repo_root} while "
            "recording the clean-run baseline -- this is not a normal "
            "pass/fail exit, so the baseline did not complete: "
            f"{result.stderr.strip() or result.stdout.strip()!r}"
        )
    return result.stdout


def main(argv=None):
    """Run the gate and print the result as JSON for the calling agent."""
    parser = argparse.ArgumentParser(description="Run the test-quality mutation gate.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--scope", choices=("merge-base", "working-tree", "full"), default="merge-base"
    )
    arguments = parser.parse_args(argv)

    # Deferred on purpose — do not hoist to module top. Both modules import
    # this one back: the backend modules need `Survivor`, and the reporter
    # needs `is_survivor`. A module-level import here closes that cycle.
    from mutation_gate_backends import default_backends
    from mutation_gate_report import as_report_payload

    paths = changed_paths(arguments.repo_root, scope=arguments.scope)
    dirty = arguments.scope == "working-tree"
    with scratch_workspace(arguments.repo_root, dirty=dirty) as workspace:
        baseline_failures, baseline_error = _record_baseline(
            workspace, _pytest_run_suite
        )
        result = run_gate(
            workspace,
            paths,
            default_backends(),
            baseline_failures=baseline_failures,
            baseline_error=baseline_error,
        )
    print(json.dumps(as_report_payload(result, scope=arguments.scope), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
