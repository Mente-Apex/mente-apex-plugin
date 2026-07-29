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

STATUS_MAP = {
    "Survived": "survived",
    "Timeout": "timeout",
    "NoCoverage": "no_coverage",
}


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
