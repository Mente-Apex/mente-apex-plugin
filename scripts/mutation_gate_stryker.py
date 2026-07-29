"""The JS/TS backend: read Stryker's JSON report.

Spike 2026-07-29, @stryker-mutator/core + vitest-runner on Node 24.18.0 (fnm).
The report at reports/mutation/mutation.json carries, per mutant, a status, a
mutatorName, a replacement, killedBy, coveredBy, and a line/column location;
testFiles[].tests[] resolves those ids to names.

`coverageAnalysis: "perTest"` is what produces coveredBy at all, so a generated
config that omits it yields a report with no test association — which would
silently disable the survivor policy. Hence default_config pins it.

Status handling, fix round 1: `Killed` is the only status silently dropped —
it is the clean success case. Every other non-Survived status Stryker can
emit (`Timeout`, `NoCoverage`, `CompileError`, `RuntimeError`, `Ignored`,
`Pending`) is exactly as inconclusive as a timeout, so each lands as a
Survivor whose `status` names it, keeping it visible in the report's
Inconclusive section instead of vanishing like a kill. A status this module
has never seen (schema drift, an unreleased Stryker version) raises rather
than silently shrinking the survivor list — the one failure mode a survivor
reporter cannot afford, since silence there is indistinguishable from "the
suite is fine."
"""

import warnings

from mutation_gate import Survivor

KILLED_STATUS = "Killed"

STATUS_MAP = {
    "Survived": "survived",
    "Timeout": "timeout",
    "NoCoverage": "no_coverage",
    "CompileError": "compile_error",
    "RuntimeError": "runtime_error",
    "Ignored": "ignored",
    "Pending": "pending",
}


def _test_names(report):
    """Map Stryker's test ids to human names, across all test files."""
    names = {}
    for test_file in report.get("testFiles", {}).values():
        for test in test_file.get("tests", []):
            names[test["id"]] = test["name"]
    return names


def _associated_tests(test_ids, names, path, mutant_id):
    """Resolve covering test ids to names, warning about any id the report
    never named rather than silently understating coverage.

    A coveredBy id absent from testFiles is a real inconsistency in the
    report itself — surfacing it costs nothing and catches it early, while
    the survivor's own associated_tests stays accurate (just the resolvable
    names).
    """
    resolved = []
    for test_id in test_ids:
        if test_id in names:
            resolved.append(names[test_id])
        else:
            warnings.warn(
                f"mutant {mutant_id!r} in {path!r} is covered by test id "
                f"{test_id!r}, which is not in testFiles; dropping it from "
                "associated_tests",
                stacklevel=2,
            )
    return tuple(resolved)


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

    `Killed` is the only status silently dropped — the clean success case.
    Timeouts, compile errors, runtime errors, ignored and pending mutants all
    come through as their own status rather than being dropped: none of them
    is a kill or a clean survival, and counting any of them either way is a
    lie the operator cannot see. A status this module doesn't recognize
    raises, because silently shrinking the survivor list on schema drift is
    worse than a hard failure.
    """
    names = _test_names(report)
    survivors = []
    for path, file_report in report.get("files", {}).items():
        for mutant in file_report.get("mutants", []):
            raw_status = mutant.get("status")
            if raw_status == KILLED_STATUS:
                continue
            status = STATUS_MAP.get(raw_status)
            if status is None:
                raise ValueError(
                    f"unrecognized Stryker mutant status {raw_status!r} for "
                    f"mutant {mutant.get('id')!r} in {path!r}; STATUS_MAP "
                    "needs updating"
                )
            start = mutant.get("location", {}).get("start", {})
            survivors.append(
                Survivor(
                    artifact=path,
                    location=f"{path}:{start.get('line')}:{start.get('column')}",
                    mutant=f"{mutant['mutatorName']} -> {mutant['replacement']}",
                    associated_tests=_associated_tests(
                        mutant.get("coveredBy", ()), names, path, mutant.get("id")
                    ),
                    backend="stryker",
                    granularity="line",
                    status=status,
                )
            )
    return tuple(survivors)
