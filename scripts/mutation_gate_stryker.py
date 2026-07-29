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

import json
import shutil
import subprocess
import warnings
from pathlib import Path

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


# Stryker reads the first of these it finds. Any of them means the audited repo
# has made its own configuration decision, which the gate never overrides --
# same rule `_configure_source_paths` follows for an existing `[tool.mutmut]`.
_CONFIG_NAMES = (
    "stryker.conf.json",
    "stryker.config.json",
    "stryker.conf.js",
    "stryker.config.js",
    "stryker.conf.mjs",
    "stryker.config.mjs",
    "stryker.conf.cjs",
    "stryker.config.cjs",
    ".stryker.conf.json",
)

GENERATED_CONFIG_NAME = "stryker.conf.json"

# The runner plugin a repo declares is what tells the generated config which
# `testRunner` to name. Guessing wrong produces a config Stryker rejects, so an
# undeclared runner means "not available" with a hint, not a guess.
_RUNNERS = {
    "@stryker-mutator/vitest-runner": "vitest",
    "@stryker-mutator/jest-runner": "jest",
    "@stryker-mutator/mocha-runner": "mocha",
    "@stryker-mutator/karma-runner": "karma",
    "@stryker-mutator/jasmine-runner": "jasmine",
}


def _existing_config(repo_root):
    """The audited repo's own Stryker config, if it has one."""
    root = Path(repo_root)
    for name in _CONFIG_NAMES:
        if (root / name).is_file():
            return root / name
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            if "stryker" in json.loads(package_json.read_text(encoding="utf-8")):
                return package_json
        except json.JSONDecodeError, OSError:
            return None
    return None


def _declared_test_runner(repo_root):
    """The `testRunner` name implied by the repo's declared runner plugin."""
    package_json = Path(repo_root) / "package.json"
    if not package_json.is_file():
        return None
    try:
        manifest = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return None
    declared = {
        **manifest.get("dependencies", {}),
        **manifest.get("devDependencies", {}),
    }
    for package, runner in _RUNNERS.items():
        if package in declared:
            return runner
    return None


def _configure(repo_root, paths):
    """Write a `stryker.conf.json` into the workspace when the repo has none.

    Exactly the role `_configure_source_paths` plays for mutmut, and for the
    same reason: `npx stryker run` in an unconfigured repo fails outright, so
    without this `available()` could return True for a partition that could
    never actually run and the whole JS side degraded to a run error the
    operator had no way to act on.

    Derived from the real selection rather than a fixed source tree, so the
    `mutate` globs track the partition Stryker is invoked over run to run.
    The workspace is a scratch copy, so this never touches the operator's tree
    -- and a repo that configures Stryker itself is left exactly as written.
    """
    if _existing_config(repo_root) is not None:
        return
    runner = _declared_test_runner(repo_root)
    if runner is None:
        return
    (Path(repo_root) / GENERATED_CONFIG_NAME).write_text(
        json.dumps(default_config(paths, runner), indent=2) + "\n",
        encoding="utf-8",
    )


def _npx_argv():
    """The npx invocation, routed through the fnm-resolved Node.

    A bare `npx` resolves through PATH to whichever `node` happens to be
    active in the shell that launched the gate -- not necessarily the version
    fnm would select for this repo (its `.node-version`/`.nvmrc`, or the
    default alias). `fnm exec -- <cmd>` re-resolves the same way fnm itself
    would before running the command, so Stryker always runs under the
    fnm-selected Node rather than whatever system Node happens to be first on
    PATH. Falls back to plain `npx` only when fnm itself is not installed at
    all, so a machine without fnm degrades rather than crashing outright.
    """
    if shutil.which("fnm"):
        return ["fnm", "exec", "--", "npx"]
    return ["npx"]


class StrykerBackend:
    """Invokes Stryker under the fnm-selected Node and reads its JSON report."""

    stack = "js"
    tool = "stryker"

    def __init__(self):
        self._run_errors = ()

    def available(self, repo_root):
        """True only when this backend can ACTUALLY run, not merely import.

        Stryker being installed is not sufficient: `npx stryker run` in a repo
        with no config fails outright. The gate can generate a config
        (`_configure`), but only if the repo declares a runner plugin whose
        `testRunner` name it recognises -- guessing one produces a config
        Stryker rejects. So availability is "installed AND (already configured
        OR configurable)". Anything less reported a partition as runnable and
        then degraded it to a run error the operator could not act on.
        """
        if not (Path(repo_root) / "node_modules" / "@stryker-mutator").is_dir():
            return False
        return (
            _existing_config(repo_root) is not None
            or _declared_test_runner(repo_root) is not None
        )

    def install_hint(self, repo_root):
        return (
            "npm install -D @stryker-mutator/core plus a runner plugin "
            "(@stryker-mutator/vitest-runner or -jest-runner), under the "
            "fnm-selected Node -- or add a stryker.conf.json naming your own "
            'testRunner with "coverageAnalysis": "perTest"'
        )

    def run_errors(self, repo_root):
        """Run-level facts from the most recent `survivors()` call.

        Empty unless that call's `stryker run` never produced a report --
        see `survivors()`. The mutmut backend's equivalent crash (collection
        never writing its stats file) is held to the same standard: named
        once here rather than silently read as "no survivors".
        """
        return self._run_errors

    def survivors(self, repo_root, paths):
        """Run Stryker over the workspace and parse its JSON report.

        A missing report after `stryker run` is not silently folded into "no
        survivors" -- that would be indistinguishable from a clean run to
        anyone reading the rendered report. The run's exit status and stderr
        are surfaced via `run_errors()` (and still via a warning, for anyone
        capturing Python warnings) rather than being swallowed into an empty
        result that looks identical to a genuinely clean run.
        `survivors_from_report` itself still raises on an unrecognised
        Stryker status rather than being caught here -- that is the gate
        misunderstanding its own data, not a missing tool, and it must fail
        loudly.
        """
        _configure(repo_root, paths)
        run_result = subprocess.run(
            _npx_argv() + ["stryker", "run"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        report_path = Path(repo_root) / "reports" / "mutation" / "mutation.json"
        if not report_path.is_file():
            self._run_errors = (
                f"stryker run did not complete in {repo_root} -- it produced "
                f"no report at {report_path} after `stryker run` exited "
                f"{run_result.returncode}, so no result from this partition "
                f"can be trusted (stderr: {run_result.stderr.strip()!r})",
            )
            warnings.warn(self._run_errors[0], stacklevel=2)
            return ()
        self._run_errors = ()
        return survivors_from_report(
            json.loads(report_path.read_text(encoding="utf-8"))
        )
