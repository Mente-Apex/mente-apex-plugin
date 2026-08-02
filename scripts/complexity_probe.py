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

from complexity_probe_gate import CycleGate
from complexity_probe_lizard import LizardProbe
from complexity_probe_measurement import UNVERIFIED, Measurement
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


def _paths_to_measure(arguments):
    """Turn the parsed arguments into the paths a probe should measure.

    A single positional argument is routed through `resolve_scope` so a range
    like "OrderService.java:40-120" still works. Two or more positional
    arguments are taken as literal paths and go straight to the probe, with no
    call to `resolve_scope` at all: its return value would be discarded either
    way (the caller already named exact files), and now that scope resolution
    can raise (task 4), making that call anyway would mean an unrelated git
    failure aborting a request that never needed git in the first place. A
    bare invocation, or `--scope`, resolves through the same vocabulary
    scripts/mutation_gate.py uses.
    """
    if len(arguments.paths) == 1:
        return resolve_scope(arguments.paths[0], repo_root=arguments.repo_root).paths
    if arguments.paths:
        return tuple(arguments.paths)
    return resolve_scope(arguments.scope, repo_root=arguments.repo_root).paths


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    thresholds = discover_thresholds(arguments.repo_root)
    probe = LizardProbe()

    try:
        paths = _paths_to_measure(arguments)
    except (ValueError, RuntimeError) as error:
        # A failure to determine scope is itself an unverified outcome: report
        # it as data, with the cause attached, rather than let it crash the
        # run or vanish into an empty (and indistinguishable from "no
        # changes") path list.
        measurement = Measurement(
            status=UNVERIFIED, reason=f"scope could not be resolved: {error}"
        )
    else:
        measurement = probe.measure(paths)

    # Evaluate the verdict if --gate is passed, before rendering so JSON can include it.
    verdict = None
    if arguments.gate:
        verdict = CycleGate().evaluate(measurement, probe.is_available())

    if arguments.json:
        artifact = ArtifactSink().render(measurement, thresholds)
        # In JSON mode, include the verdict in the payload so the entire output is valid JSON.
        if verdict:
            artifact["verdict"] = {"status": verdict.status, "message": verdict.message}
        print(json.dumps(artifact, indent=2))
    else:
        sink = TranscriptSink() if arguments.sink == "transcript" else ReviewSink()
        print(sink.render(measurement, thresholds))
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
