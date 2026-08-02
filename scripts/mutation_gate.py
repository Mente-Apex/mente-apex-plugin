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
from pathlib import Path
from typing import Protocol, runtime_checkable

from mutation_gate_scope import changed_paths
from mutation_gate_workspace import scratch_workspace

STACK_SUFFIXES = {
    "python": (".py",),
    "js": (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"),
    "java": (".java", ".kt", ".scala"),
    "prose": (".md",),
}

# Every subprocess this gate starts runs somebody else's code -- the audited
# repo's test suite, or a mutation tool driving it -- so none of them may block
# forever. Generous, because a real suite under mutation is slow, but finite:
# an unbounded wait leaves the gate hung inside a scratch workspace that is
# still registered as a worktree against the operator's repo, with no report
# ever written and nothing to say why.
SUITE_TIMEOUT_SECONDS = 1800


@dataclass(frozen=True)
class Survivor:
    """One mutant the suite failed to kill.

    `granularity` records what the backend could actually tell us — Stryker
    resolves a survivor to a line and the tests that covered it, mutmut only to
    the mutated function. The report states which, rather than implying a
    precision the backend never had.

    `status` is a CLOSED vocabulary. Every value the backends emit today:

    - `survived` — the mutant lived and the finding is real. mutmut emits it
      for its own `survived` status; the prose backend emits it for every
      operator except `invert`; Stryker maps `Survived` to it.
    - `survived_minor` — prose only, and only for the `invert` operator:
      presence-only guards legitimately survive inversion, so that operator
      reports at a lower tier.
    - `no_op_mutant` — prose only: the operator left the declared slice
      byte-identical, so no mutant was ever applied and the test was never
      run. Not a survivor (nothing survived), but reported rather than
      dropped, so "this operator had nothing to change here" stays
      distinguishable from "it ran and the guard killed it".
    - `declaration_error` — prose only: the `@pytest.mark.covers` declaration
      could not be resolved (a heading renamed out from under it, an artifact
      that no longer exists), so none of its operators ever produced a mutant.
      Reported as one inconclusive row rather than raised, because it is one
      declaration's problem: raising took down the whole run and discarded
      every survivor the other backends had already collected.
    - `unreliable_baseline` — assigned by `run_gate`, not by a backend, when
      every test covering the survivor was already red before any mutant ran.
    - `timeout`, `no_coverage`, `compile_error`, `runtime_error`, `ignored`,
      `pending` — Stryker's `STATUS_MAP`. A status Stryker emits that the map
      does not know raises rather than being dropped.
    - `non_viable`, `memory_error` — PIT's `STATUS_MAP`, which otherwise reuses
      the vocabulary above: `NO_COVERAGE`, `TIMED_OUT` and `RUN_ERROR` map onto
      `no_coverage`, `timeout` and `runtime_error` rather than growing
      backend-specific synonyms for the same fact. The two here have no
      equivalent — `NON_VIABLE` means the mutated bytecode never loaded, so no
      test ever ran against it, and `MEMORY_ERROR` means the mutant exhausted
      the heap rather than being caught. Like Stryker's, an unrecognised PIT
      status raises rather than being dropped.
    - `skipped`, `suspicious`, `segfault`, `no tests`, `not checked`,
      `caught by type check`, `check was interrupted by user` — mutmut's own
      non-`killed`/non-`survived` statuses (`status_by_exit_code` in mutmut's
      `__main__.py`); `killed` is mutmut's only silent drop. A status mutmut
      emits that this module has never seen raises rather than being dropped.

    Use `is_survivor()` to classify — never compare `status` by hand, or the
    vocabulary drifts out of sync across the consumers again.

    `survived_minor` IS a survivor, at a lower tier than plain `survived` --
    the report must say so (both `render_markdown` and `as_report_payload`
    surface `status` on it) rather than either folding it in as an
    indistinguishable plain survivor or dropping it into "Inconclusive",
    which would misreport a real finding as no finding at all.
    """

    artifact: str
    location: str
    mutant: str
    associated_tests: tuple[str, ...]
    backend: str
    granularity: str
    mutant_diff: str = ""
    status: str = "survived"


# `survived_minor` is a real survivor at a lower tier (the prose backend's
# deliberate `invert`-operator tiering) -- it belongs here, not with the
# inconclusive statuses. See the Survivor docstring above.
SURVIVED_STATUSES = frozenset({"survived", "survived_minor"})

# Statuses recording a mutant that was NEVER APPLIED. They are reported so the
# absence stays visible, but they are not part of the population
# `BackendRun.mutants_executed` counts, and conflating the two broke the
# all-inconclusive derivation in both directions: one `no_op_mutant` was enough
# to make a run where pytest answered nothing report as clean, and enough to
# make a run whose mutants were genuinely killed report as verifying nothing.
NOT_EXECUTED_STATUSES = frozenset({"no_op_mutant", "declaration_error"})


def was_executed(survivor):
    """True when this row records a mutant that was actually applied and run."""
    return survivor.status not in NOT_EXECUTED_STATUSES


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

    # Optional: a backend may implement `run_errors(repo_root) -> tuple[str,
    # ...]` to report that its own tool run did not complete this call to
    # `survivors()` (e.g. mutmut's stats collection crashing before a single
    # mutant executed) -- one named fact per such failure, not expanded into
    # a row per mutant it never got to check. `run_gate` calls it only when
    # present (`getattr(backend, "run_errors", None)`), so a backend or test
    # double that has no run-level failure mode of its own need not implement
    # it.

    # Optional, and strongly recommended: a backend may implement
    # `mutants_executed(repo_root) -> int | None` reporting how many mutants
    # its most recent `survivors()` call actually applied and ran. Without it
    # an empty survivor list cannot be told apart from a run that generated no
    # mutants at all, so a backend that does not implement it FORFEITS that
    # check -- `run_gate` records the omission (`BackendRun.counts_mutants`)
    # and `unverified_reasons` stays silent about it rather than condemning
    # every conformant backend that simply never claimed to count. A backend
    # that DOES implement it and returns None is saying it tried and could not,
    # which is a reason. All four shipped backends implement it.

    # Optional: a backend may implement `scope_notes(repo_root) -> tuple[str,
    # ...]` to report that its run COMPLETED but covered something other than
    # the selection it was handed -- pitest falling back to the project's own
    # `targetClasses` because a selected path could not be resolved to a class,
    # for instance. This is deliberately NOT `run_errors`: the tool ran and its
    # per-mutant results are trustworthy, so the report must not print the
    # "this run did not complete" banner over them. What it must not do either
    # is stay silent, because "no survivors over a narrower scope than you
    # asked for" renders identically to "no survivors". Collected the same way
    # `run_errors` is, so a backend without the failure mode need not implement
    # it.


@dataclass(frozen=True, kw_only=True)
class BackendRun:
    """What one backend's invocation of its tool actually covered.

    `mutants_executed` is how many mutants the tool applied and ran a test
    against during THIS call. It exists because a survivor list cannot answer
    the one question that decides whether an empty one means anything: a run
    that generated zero mutants and a run that generated fifty and killed all
    fifty both report no survivors, no run errors and no inconclusive
    results. Without a count they are the same bytes, and the first is a
    vacuous pass over code nothing tested.

    `None` is deliberately distinct from `0`. `0` is a tool that ran and
    mutated nothing (a `mutate` glob matching no file, a source path the
    parser choked on); `None` is a backend that does not report the number at
    all, so the question is unanswered rather than answered badly. Both stop
    `unverified_reasons` from calling the run clean, and they say different
    things to the operator about why.
    """

    stack: str
    tool: str
    mutants_executed: int | None = None
    # Whether the backend implements `mutants_executed` AT ALL, which is a
    # different question from what it answered. The method is optional on the
    # Backend Protocol, and treating its absence as a blocking "unanswered"
    # made every conformant backend that does not implement it -- including
    # any test double -- exit 2 forever. A backend that never claimed to count
    # forfeits the vacuous-run check; one that claims to and returns None
    # tried and could not say, which IS a reason.
    counts_mutants: bool = False


@dataclass(frozen=True, kw_only=True)
class GateResult:
    """What one gate run produced.

    Keyword-only, deliberately. Seven fields, several interchangeable at the
    type level -- `unresolved` and `unclaimed` are both `tuple[str, ...]`, as
    are `baseline_failures` and `run_errors` -- so a positional transposition
    would misfile an entire category of finding, type-check clean, and render
    a plausible-looking report. Every call site names its fields.

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

    `run_errors` is `baseline_error`'s sibling for a *backend's* run rather
    than the baseline: one named fact per backend whose own tool run did not
    complete (mutmut's stats collection crashing before a single mutant
    executed is the reproduced case). It is a tuple, not a single string like
    `baseline_error`, because more than one backend can run in the same
    invocation (a mixed Python/JS repo) and each is independent. This is
    deliberately NOT where a completed run's genuine per-mutant inconclusive
    results go -- those still arrive as ordinary `Survivor`s in `survivors`
    with their own `status` (see `Survivor`'s docstring); `run_errors` exists
    only for the run-level case where no individual mutant result can be
    trusted at all, so a single system failure is reported once instead of
    being fanned out into one row per mutant it never got to check.

    `selected` is how many paths the run was actually handed. Without it, a
    zero-file scope (a clean tree under `--scope working-tree`) is an all-empty
    result indistinguishable from a scope full of files where nothing survived
    -- "nothing to do" reading as "nothing found" is the same
    silence-as-a-pass this dataclass exists to close, one level up.
    """

    survivors: tuple[Survivor, ...]
    unavailable: tuple[tuple[str, str], ...]
    unresolved: tuple[str, ...]
    unclaimed: tuple[str, ...]
    baseline_failures: tuple[str, ...] = ()
    baseline_error: str = ""
    run_errors: tuple[str, ...] = ()
    scope_notes: tuple[str, ...] = ()
    selected: int = 0
    backend_runs: tuple[BackendRun, ...] = ()


def unverified_reasons(result):
    """Why an empty survivor list from this run may not be read as clean.

    Empty means the run genuinely verified the scope and found nothing. Any
    entry means it did not look -- or could not finish looking -- so "no
    survivors" is an absence of data rather than a result.

    Single-sourced deliberately. The renderer needs it to decide whether to
    print the clean-run sentence, and `main` needs it to decide an exit code;
    two independent judgements of the same question is how they drift and one
    of them starts calling a broken run clean again. Returns operator-facing
    strings rather than a bare bool so the report can say WHICH of these
    happened without re-deriving it.

    `selected == 0` is NOT here. A scope with no files in it is an honest
    "nothing to do", not a failure to look, and it has its own sentence.
    """
    reasons = []
    if result.baseline_error:
        reasons.append(
            "the clean-run baseline never completed, so no kill from this "
            "run is trustworthy"
        )
    for message in result.run_errors:
        # First line only. A `run_errors` message may carry a multi-KB tool
        # dump, and the report already renders that once, bounded, in its own
        # section -- repeating it verbatim here would splice the whole dump
        # back in unbounded and undo that bounding.
        summary = message.splitlines()[0] if message else message
        reasons.append(f"a backend's tool run did not complete: {summary}")
    for stack, hint in result.unavailable:
        reasons.append(
            f"no {stack} mutation tool was available, so the {stack} files in "
            f"scope were never mutated (declare it with `{hint}`)"
        )
    if result.unclaimed:
        reasons.append(
            f"{len(result.unclaimed)} file(s) landed in a known stack with no "
            "backend registered for it, so they were never mutated"
        )
    counting_runs = [
        backend_run for backend_run in result.backend_runs if backend_run.counts_mutants
    ]
    for backend_run in counting_runs:
        if backend_run.mutants_executed is None:
            # Suppressed when the run already failed loudly: a crashed backend
            # sets its count to None precisely BECAUSE it crashed, so saying
            # "it could not say how many mutants it applied" alongside the
            # crash is a second, misleading account of one event.
            if not result.run_errors:
                reasons.append(
                    f"{backend_run.tool} could not say how many mutants it "
                    "applied, so an empty survivor list from it cannot be "
                    "distinguished from a run that mutated nothing"
                )
        elif backend_run.mutants_executed == 0:
            reasons.append(
                f"{backend_run.tool} ran but applied no mutants at all, so it "
                "tested nothing"
            )

    counted = [
        backend_run.mutants_executed
        for backend_run in counting_runs
        if backend_run.mutants_executed is not None
    ]
    if counted and len(counted) == len(counting_runs):
        executed = sum(counted)
        # Only rows recording a mutant that ACTUALLY RAN belong in this
        # arithmetic. `mutants_executed` excludes never-applied mutants, so
        # comparing it against the whole survivor list compared two different
        # populations: a single `no_op_mutant` broke the equality, and with it
        # both directions of this check. See `NOT_EXECUTED_STATUSES`.
        executed_rows = [
            survivor for survivor in result.survivors if was_executed(survivor)
        ]
        killed = executed - len(executed_rows)
        # Every mutant that ran came back inconclusive -- a coverage analysis
        # that misfired, a suite that could not answer under any mutant --
        # which is not a clean sweep however much it renders like one.
        if (
            executed
            and killed <= 0
            and not any(is_survivor(survivor) for survivor in executed_rows)
        ):
            reasons.append(
                f"all {executed} mutant(s) that ran came back inconclusive -- "
                "none was killed and none survived, so nothing was actually "
                "verified"
            )
    return tuple(reasons)


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

    paths = tuple(paths)
    partitions = partition(paths)
    survivors = []
    unavailable = []
    unclaimed = []
    run_errors = []
    scope_notes = []
    backend_runs = []
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
        backend_run_errors = getattr(backend, "run_errors", None)
        if backend_run_errors is not None:
            run_errors.extend(backend_run_errors(repo_root))
        backend_scope_notes = getattr(backend, "scope_notes", None)
        if backend_scope_notes is not None:
            scope_notes.extend(backend_scope_notes(repo_root))
        count_reporter = getattr(backend, "mutants_executed", None)
        backend_runs.append(
            BackendRun(
                stack=stack,
                tool=backend.tool,
                mutants_executed=(
                    count_reporter(repo_root) if count_reporter is not None else None
                ),
                counts_mutants=count_reporter is not None,
            )
        )

    already_red = set(baseline_failures)
    marked = tuple(
        (
            replace(survivor, status="unreliable_baseline")
            if survivor.associated_tests
            and all(
                _is_already_red(test, already_red) for test in survivor.associated_tests
            )
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
        run_errors=tuple(run_errors),
        scope_notes=tuple(scope_notes),
        selected=len(paths),
        backend_runs=tuple(backend_runs),
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


_ALREADY_RED_PREFIXES = ("FAILED ", "ERROR ")


def _failed_node_ids(output):
    """Parse pytest's `-rfE` short summary into what was already red.

    Both prefixes, deliberately. `-rf` alone reports only outright test
    FAILURES; a test that ERRORS -- a broken fixture, a module-level import
    blowing up, a collection error -- is summarised under `ERROR` and appears
    only with `-rE`. Its exit code is 1, indistinguishable from an ordinary
    failing test, so `_pytest_run_suite`'s exit-code guard does not catch it
    either. Parsing only `FAILED` therefore recorded an errored test as a
    CLEAN baseline, and every mutant whose covering test errored again under
    mutation was scored as killed -- the exact phantom kill `baseline()`
    exists to prevent.

    An `ERROR` line may name a whole file rather than a node id (a collection
    error has no node to blame). That is kept as-is; `_is_already_red` treats
    a bare file entry as covering every node id beneath it.
    """
    node_ids = []
    for line in output.splitlines():
        for prefix in _ALREADY_RED_PREFIXES:
            if line.startswith(prefix):
                remainder = line[len(prefix) :]
                node_ids.append(remainder.split(" - ", 1)[0].strip())
                break
    return tuple(node_ids)


def _is_already_red(node_id, already_red):
    """True when `node_id` was failing before any mutant was applied.

    An exact match is the ordinary case. A collection error, though, is
    reported against the FILE -- pytest has no node to name when the module
    never imported -- and every test in that file was equally red. Matching
    the file part as well is what stops a whole errored module's tests from
    reading as clean covering tests.
    """
    if node_id in already_red:
        return True
    return node_id.split("::", 1)[0] in already_red


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

    `-rfE`, not `-rf`: an errored test exits 1 like an ordinary failure and so
    slips past the guard above, but is summarised under `ERROR` rather than
    `FAILED`. See `_failed_node_ids`.

    A timeout, because the audited repo's suite is arbitrary code: one test
    blocking on a socket would otherwise hang the gate forever, inside a
    scratch workspace still registered as a worktree against the operator's
    repo. A hung baseline is a baseline that did not complete, so it takes the
    same route to the report as any other broken baseline.
    """
    try:
        result = subprocess.run(
            ["uv", "run", "pytest", "--tb=no", "-q", "-rfE"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=SUITE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise BaselineRunFailedError(
            f"uv run pytest did not finish within {SUITE_TIMEOUT_SECONDS}s in "
            f"{repo_root} while recording the clean-run baseline, so the "
            "baseline did not complete"
        ) from exc
    if result.returncode not in (0, 1):
        raise BaselineRunFailedError(
            f"uv run pytest exited {result.returncode} in {repo_root} while "
            "recording the clean-run baseline -- this is not a normal "
            "pass/fail exit, so the baseline did not complete: "
            f"{result.stderr.strip() or result.stdout.strip()!r}"
        )
    return result.stdout


def main(argv=None):
    """Run the gate, print the JSON payload, and (with `--report`) write the
    report section.

    Both outputs, not one: the JSON on stdout is what the analyzer agent
    parses, and the spliced markdown is what a human reads. This lens holds
    the report to be the single source of truth, so a survivor that only ever
    reached stdout would be invisible to the person the finding is for.

    Writing the report is the CLI's job rather than an instruction to the
    reviewer agent, deliberately. The marker contract is then exercised by a
    test (`tests/test_mutation_gate_cli_report.py`) instead of resting on
    prose an agent may or may not follow -- which is precisely the
    unverifiable-guard failure mode this whole feature exists to catch. A
    prose instruction to "paste the section in" is a guard nothing can check.

    `--report` is opt-in, so a default run still writes nothing anywhere near
    the operator's tree: the byte-identical guarantee is unchanged for every
    invocation that does not explicitly name a file to update.
    """
    parser = argparse.ArgumentParser(description="Run the test-quality mutation gate.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--scope", choices=("merge-base", "working-tree", "full"), default="merge-base"
    )
    parser.add_argument(
        "--report",
        default=None,
        help=(
            "Path to a report carrying the mutation-gate markers; the gate "
            "replaces the span between them with this run's section. Omitted, "
            "the gate writes no file at all."
        ),
    )
    arguments = parser.parse_args(argv)

    # Deferred on purpose — do not hoist to module top. Both modules import
    # this one back: the backend modules need `Survivor`, and the reporter
    # needs `is_survivor`. A module-level import here closes that cycle.
    from mutation_gate_backends import default_backends
    from mutation_gate_report import (
        as_report_payload,
        render_markdown,
        splice_into_report,
    )

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
    if arguments.report is not None:
        # After the JSON, never before: a missing report file or a report with
        # no markers raises, and the analyzer's copy of the result must not be
        # lost to a report-writing problem. The raise itself stays uncaught --
        # a gate that silently fails to write its findings is the exact
        # silence this feature exists to remove.
        report_path = Path(arguments.report)
        report_path.write_text(
            splice_into_report(
                report_path.read_text(encoding="utf-8"),
                render_markdown(result, scope=arguments.scope),
            ),
            encoding="utf-8",
        )
    return exit_code_for(result)


def exit_code_for(result):
    """0 only when this run looked and found nothing.

    Non-zero for a survivor (there is a finding) and non-zero for a run that
    could not verify its scope (`unverified_reasons`) -- an unavailable tool,
    a crashed backend, a broken baseline, a run that mutated nothing. Always
    returning 0 meant any shell or CI step reading the exit code recorded
    every run as a pass, including the runs that never mutated a line, and the
    verdict lived only in output nothing was checking.

    Distinct codes so a caller can tell the two apart: a survivor is a real
    finding to act on, an unverified run is a gate to fix before its silence
    means anything.
    """
    if unverified_reasons(result):
        return 2
    if any(is_survivor(survivor) for survivor in result.survivors):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
