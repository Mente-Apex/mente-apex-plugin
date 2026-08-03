"""The complexity probe's command line.

Composition root: the only place concrete probes, sinks and threshold sources
are chosen. Everything below this file takes its collaborators as arguments,
which is why the verdict logic is testable without a subprocess.

`--scope` shares its vocabulary with scripts/mutation_gate.py so the two
sensors are asked for a target the same way.

Scope resolution now delegates to a git query that fails loudly (see
scripts/mutation_gate_scope.py): no default branch, or a non-zero git exit,
raises rather than quietly returning an empty path list. An empty list and "I
could not tell you what changed" are not the same fact, and conflating them is
exactly the silence spec §2.3 forbids. So this file is also the only place
that catches a scope failure and turns it into an `unverified` measurement
carrying the cause — never letting the exception itself reach the user, and
never discarding the reason.

`--gate` here is a reporter, not a blocker, and that is deliberate rather than
an oversight. `CycleGate.evaluate` only blocks when the measurement it is
handed is `None` *and* the probe was available — i.e. when whatever called it
never even attempted a measurement. This CLI process always attempts one: it
either produces a real `Measurement` from the probe or synthesizes an
`unverified` one from a caught scope failure (see above), so `measurement` is
never `None` by the time `CycleGate.evaluate` is called and `verdict.blocks`
can never be true here — confirmed even with the probe made unavailable.
That is not a bug in this file's wiring; it is what "silence" *means* for
spec §2.3: the agent never ran the probe at all, and a self-contained CLI
invocation cannot observe its own non-invocation. The blocking branch stays in
`main()` because it is the correct guard for the contract — it simply cannot
fire from this entry point. It exists for a caller that genuinely can observe
silence from the outside, such as a hook reading whether this probe's
transcript output appears at all in a cycle's record. Do not read the
unreachable branch here as dead code to delete.
"""

import argparse
import json
import sys
from dataclasses import replace

from complexity_probe_gate import CycleGate
from complexity_probe_lizard import LizardProbe
from complexity_probe_measurement import UNVERIFIED, Measurement
from complexity_probe_scope import ScopeSelection, resolve_literal_paths, resolve_scope
from complexity_probe_sinks import ArtifactSink, ReviewSink, TranscriptSink
from complexity_probe_thresholds import discover_thresholds, no_thresholds_because


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
        help="apply the cycle-gate verdict and report it (see module docstring: "
        "this entry point cannot itself observe silence, so it cannot block)",
    )
    parser.add_argument(
        "--sink",
        choices=("transcript", "review"),
        default="transcript",
        help="which rendering to print (ignored with --json)",
    )
    return parser


def _selection_to_measure(arguments) -> ScopeSelection:
    """Turn the parsed arguments into the selection a probe is asked for.

    A single positional argument is routed through `resolve_scope` so a range
    like "OrderService.java:40-120" still works. Two or more positional
    arguments are taken as literal paths and go through `resolve_literal_paths`
    rather than `resolve_scope`: the latter's return value would be discarded
    either way (the caller already named exact files), and now that scope
    resolution can raise, making that call anyway would mean an unrelated git
    failure aborting a request that never needed git in the first place.
    `resolve_literal_paths` asks the filesystem whether the named paths are
    there and asks git nothing, so both properties hold at once. A bare
    invocation, or `--scope`, resolves through the same vocabulary
    scripts/mutation_gate.py uses.

    The whole `ScopeSelection` comes back, not just its paths. The line range
    is here because a probe measures a file, not a slice of one: narrowing to
    the requested lines is this composition root's job, not the probe's. The
    description is here because "no functions" is otherwise two different
    facts wearing the same words — an empty file, and a range that selected
    nothing — and only the selection knows which one happened.
    """
    if len(arguments.paths) == 1:
        return resolve_scope(arguments.paths[0], repo_root=arguments.repo_root)
    if arguments.paths:
        return resolve_literal_paths(arguments.paths)
    return resolve_scope(arguments.scope, repo_root=arguments.repo_root)


def _overlaps_line_range(metric, line_range) -> bool:
    """Whether a measured function intersects the requested line range.

    Overlap, deliberately, not containment. A function that straddles the
    boundary of the requested chunk is part of that chunk — it is very often
    the function the reviewer's cursor is sitting in — and dropping it would
    reproduce the failure this scoping exists to fix, only in the other
    direction: a confident report that omits the target.
    """
    requested_start, requested_end = line_range
    return metric.start_line <= requested_end and metric.end_line >= requested_start


def _narrowed_to_line_range(measurement, line_range):
    """The same measurement carrying only the functions inside `line_range`.

    Without this, `File.py:1-2` reported every function in File.py — the
    caller's scope parsed, echoed and then discarded, which is a confident
    number attributed to the wrong target. Three shipped surfaces advertise
    the range form, so it has to mean something.
    """
    if line_range is None:
        return measurement
    return replace(
        measurement,
        functions=tuple(
            metric
            for metric in measurement.functions
            if _overlaps_line_range(metric, line_range)
        ),
    )


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)

    try:
        thresholds = discover_thresholds(arguments.repo_root)
    except Exception as error:
        # Each source already treats a config it cannot read as absence. This
        # is the backstop that makes that invariant structural rather than
        # dependent on every future source remembering it: exit 1 is reserved
        # for a blocking gate verdict, so a repo with a typo in someone else's
        # config file must still get a measurement and a stated "no limit" —
        # never a traceback wearing the gate's reserved exit code.
        thresholds = no_thresholds_because(
            f"threshold discovery failed: {type(error).__name__}: {error}"
        )

    # Neither human sink renders threshold state, so without this a config the
    # repo declared but nobody could read would go unmentioned — indis-
    # tinguishable from a repo that declares no limit at all. `diagnostics` is
    # the only field that carries a cause: `source` names the config a limit
    # came from, which on the run that looks healthiest is some *other*,
    # perfectly readable config. stderr keeps stdout a single valid JSON
    # document.
    for diagnostic in thresholds.diagnostics:
        print(f"thresholds: {diagnostic}", file=sys.stderr)

    probe = LizardProbe()

    try:
        selection = _selection_to_measure(arguments)
    except (ValueError, RuntimeError) as error:
        # A failure to determine scope is itself an unverified outcome: report
        # it as data, with the cause attached, rather than let it crash the
        # run or vanish into an empty (and indistinguishable from "no
        # changes") path list.
        measurement = Measurement(
            status=UNVERIFIED, reason=f"scope could not be resolved: {error}"
        )
        scope_description = None
    else:
        measurement = _narrowed_to_line_range(
            probe.measure(selection.paths), selection.line_range
        )
        scope_description = selection.description

    # Evaluate the verdict if --gate is passed, before rendering so JSON can include it.
    verdict = None
    if arguments.gate:
        verdict = CycleGate().evaluate(measurement, probe.is_available())

    if arguments.json:
        artifact = ArtifactSink().render(measurement, thresholds, scope_description)
        # In JSON mode, include the verdict in the payload so the entire output is valid JSON.
        if verdict:
            artifact["verdict"] = {"status": verdict.status, "message": verdict.message}
        print(json.dumps(artifact, indent=2))
    else:
        sink = TranscriptSink() if arguments.sink == "transcript" else ReviewSink()
        print(sink.render(measurement, thresholds, scope_description))
        # In transcript/review mode, print the verdict separately to stdout.
        if verdict:
            if verdict.blocks:
                print(verdict.message, file=sys.stderr)
                return 1
            else:
                print(verdict.message)

    if verdict and verdict.blocks:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
