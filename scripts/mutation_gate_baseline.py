"""Running the audited repo's real suite, whatever language it is written in.

The gate needs one thing from the suite before it mutates a line: the set of
tests that were ALREADY red. Without it a mutant whose only covering test was
broken anyway scores as killed -- a phantom kill, which is the failure
`mutation_gate.baseline` exists to prevent.

Until this module existed that run was hardcoded to `uv run pytest`, so on a
Gradle or Maven repo it collected nothing, exited 5, and the gate returned exit
2 for every run forever (#155). The backends had been generalised across
languages; the baseline underneath them had not.

**The abstraction is `SuiteRunner`**, and the whole module is four
implementations of it plus a resolver. `mutation_gate` depends on the protocol
-- it is handed a `already_red` callable and knows nothing about pytest, Gradle
or anything else -- so a new stack is a new runner registered in
`default_suite_runners()`, never an edit to the gate.

**The honesty rule every runner honours.** `already_red()` returns the red test
identifiers, or raises `BaselineRunFailedError`. What it may never do is return
an empty tuple when the suite was red but it could not name which tests: that
reads as a clean baseline, and a clean baseline is exactly what manufactures
the phantom kills. "I could not tell" and "nothing was red" are different
answers and the gate reports them differently -- exit 2 with a stated cause
versus a verified sweep.
"""

import json
import subprocess
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Protocol, runtime_checkable

from mutation_gate import (
    SUITE_TIMEOUT_SECONDS,
    BaselineRunFailedError,
    _pytest_run_suite,
    baseline,
)
from mutation_gate_freshness import ReportFreshness
from mutation_gate_toolchain import wrapper_or_bare

# A suite run reports pass (0) or fail (1); any other code means the run itself
# broke -- a compile error, an OOM kill, a tool that was not there. The same
# guard the pytest baseline has always applied, now stated once for the runners
# that shell out to a build tool.
PASS_OR_FAIL = (0, 1)


@runtime_checkable
class SuiteRunner(Protocol):
    """One language's answer to "run the suite and tell me what was red".

    `toolchain` is the name the operator sees in a report and types after
    `--suite-runner`. `available` is detection. `already_red` runs the suite.
    Three questions, kept separate because the resolver only ever asks the
    first two and the gate only ever asks the third.
    """

    toolchain: str

    def available(self, repo_root) -> bool:
        """True when this repo's markers say this is its suite."""

    def already_red(self, repo_root) -> tuple:
        """Test identifiers failing before any mutant was applied.

        Raises `BaselineRunFailedError` when the run did not complete, or
        completed red without naming what was red.
        """


def _text_of(repo_root, name):
    """A manifest's contents, or `""` when it is absent or unreadable.

    Unreadable is treated as absent on purpose: detection that raises would
    take down the gate over a permissions quirk in a file it is only sniffing.
    """
    path = Path(repo_root) / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


class PytestSuiteRunner:
    """Python, via `uv run pytest`.

    Delegates to `mutation_gate.baseline` rather than reimplementing it: that
    function and its `-rfE` summary parser are load-bearing and already tested,
    and this class's job is detection plus a name, not a second parser.
    """

    toolchain = "pytest"

    # `pyproject.toml` alone is not enough: it says "this is a Python package",
    # not "this package has a pytest suite". Resolving on its mere presence is
    # how a repo with no pytest suite ends up running `uv run pytest` and
    # collecting nothing -- #155's own failure, reintroduced by the fix.
    _MARKER_FILES = ("pytest.ini", "conftest.py")
    _MARKED_MANIFESTS = (
        "pyproject.toml",
        "tox.ini",
        "setup.cfg",
        # A Django or Flask service routinely keeps its test deps here rather
        # than in pyproject. Without these, such a repo carrying a frontend
        # `package.json` resolved the NODE runner, whose green run returns an
        # empty already-red set -- so every Python mutant whose only covering
        # test was already failing scored as killed, silently. The old
        # hardcoded-pytest baseline would at least have exited 2 loudly.
        "requirements-dev.txt",
        "requirements-test.txt",
        "requirements.txt",
        "Pipfile",
    )

    def available(self, repo_root):
        if any((Path(repo_root) / name).is_file() for name in self._MARKER_FILES):
            return True
        if any(
            "pytest" in _text_of(repo_root, manifest)
            for manifest in self._MARKED_MANIFESTS
        ):
            return True
        # A `tests/` tree of `test_*.py` is a pytest suite whether or not any
        # manifest says so, and this is the last check rather than the first
        # because reading a manifest is cheaper than walking a tree.
        tests_directory = Path(repo_root) / "tests"
        return tests_directory.is_dir() and any(tests_directory.glob("**/test_*.py"))

    def already_red(self, repo_root):
        return baseline(repo_root, _pytest_run_suite)


def _junit_case_id(testcase):
    """`classname.name`, which is how a JVM developer names a test.

    Not PIT's `succeedingTests` spelling, which varies with the JUnit platform
    version and is absent altogether without `fullMutationMatrix`. Where the
    two do not match, `_is_already_red` simply does not fire and a survivor
    stays reported as a survivor -- the same safe direction the pitest backend
    takes with an empty `associated_tests`, over-reporting rather than
    explaining a finding away.
    """
    class_name = (testcase.get("classname") or "").strip()
    test_name = (testcase.get("name") or "").strip()
    if class_name and test_name:
        return f"{class_name}.{test_name}"
    return class_name or test_name


def _red_cases_in(report_xml):
    """Every failing or erroring case in one JUnit XML result file.

    Errors as well as failures, for the reason `-rfE` exists on the pytest
    side: a test that blew up in a fixture never ran, and a test that never ran
    is not a test that passed. Counting only `<failure>` recorded an errored
    test as a clean baseline and scored every mutant its covering test errored
    on as killed.
    """
    try:
        root = ElementTree.fromstring(report_xml)
    except ElementTree.ParseError:
        # A half-written file from a killed run. Skipped rather than fatal:
        # the sibling modules' results are still real, and a run that produced
        # nothing at all is caught by the empty-results check instead.
        return ()
    red = []
    for testcase in root.iter("testcase"):
        if testcase.find("failure") is None and testcase.find("error") is None:
            continue
        identity = _junit_case_id(testcase)
        if identity:
            red.append(identity)
    return tuple(red)


class JUnitXmlSuiteRunner:
    """A JVM build tool's test task, read back out of its JUnit XML.

    Gradle and Maven differ in three details and agree on everything else, so
    they are one class configured twice rather than two classes or a base and
    two subclasses: the differences are DATA (manifests, launcher, task, where
    results land), and encoding data as a type hierarchy is how a third JVM
    tool becomes a refactor instead of a registration.

    Every collaborator is injected. `locate_results` is the discovery strategy,
    and `freshness` is the stale-report policy -- the same `ReportFreshness`
    the pitest backend uses, for the same reason: `--scope working-tree` copies
    the operator's `build/`/`target/` into the workspace, so last week's
    results are sitting where this run's would be.
    """

    def __init__(self, toolchain, manifests, wrapper, bare, task_argv, locate_results):
        self.toolchain = toolchain
        self._manifests = manifests
        self._wrapper = wrapper
        self._bare = bare
        self._task_argv = task_argv
        self._locate_results = locate_results

    def available(self, repo_root):
        return any(
            (Path(repo_root) / manifest).is_file() for manifest in self._manifests
        )

    def already_red(self, repo_root):
        launcher = wrapper_or_bare(repo_root, self._wrapper, self._bare)
        if launcher is None:
            raise BaselineRunFailedError(
                f"neither ./{self._wrapper} nor a {self._bare} on PATH in "
                f"{repo_root}, so the {self.toolchain} suite could not be run "
                "and no clean-run baseline was recorded"
            )
        freshness = ReportFreshness(self._locate_results)
        freshness.snapshot(repo_root)
        returncode = _run(launcher + list(self._task_argv), repo_root, self.toolchain)
        written = freshness.written_since(repo_root)
        if not written:
            raise BaselineRunFailedError(
                f"the {self.toolchain} run wrote no test results under "
                f"{repo_root} -- any results already there belong to an "
                "earlier run over different code, so the baseline did not "
                "complete"
            )
        already_red = tuple(
            case_id
            for report in written
            for case_id in _red_cases_in(_read_text(report))
        )
        if returncode != 0 and not already_red:
            # The honesty rule. The build says something failed and the results
            # name nothing, so this baseline cannot tell a phantom kill from a
            # real one -- and `()` would claim it can.
            raise BaselineRunFailedError(
                f"the {self.toolchain} run reported failures (exit "
                f"{returncode}) but its test results name no failing test, so "
                "the baseline cannot say which tests were already red"
            )
        return already_red


class NodeSuiteRunner:
    """JavaScript/TypeScript, via the repo's own `npm test` script.

    Green is a usable baseline and red is not: `npm test` fans out to whatever
    runner the repo chose, whose console format is nobody's contract, so a
    failing run cannot be turned into test identifiers. That raises rather than
    returning `()` -- see the module docstring. A repo that wants a usable red
    baseline here can point `--suite-runner` at a future reporter-backed
    runner; guessing at Jest's or Vitest's output shape is how the gate would
    start inventing node ids that match nothing.
    """

    toolchain = "node"

    def available(self, repo_root):
        try:
            manifest = json.loads(_text_of(repo_root, "package.json") or "{}")
        except json.JSONDecodeError:
            return False
        # `null`, `[]`, `"a string"` and `{"scripts": null}` are all valid JSON and
        # all raised AttributeError here, killing the whole gate during DETECTION
        # -- before any mutant ran, from a file this runner was only sniffing.
        if not isinstance(manifest, dict):
            return False
        scripts = manifest.get("scripts")
        if not isinstance(scripts, dict):
            return False
        return bool(scripts.get("test"))

    def already_red(self, repo_root):
        returncode = _run(["npm", "test", "--silent"], repo_root, self.toolchain)
        if returncode == 0:
            return ()
        raise BaselineRunFailedError(
            f"npm test exited {returncode} in {repo_root}: the suite was "
            "already red and this runner cannot name which tests, so the "
            "baseline would be indistinguishable from a clean one"
        )


class UnsupportedToolchain:
    """The runner a repo resolves to when no marker matched.

    A null object rather than `None` so the caller has no branch to forget:
    the failure travels the same `_record_baseline` path as any other broken
    baseline and lands in the operator-facing report. Its whole job is to name
    the real cause -- the old failure surfaced as `uv run pytest exited 5`,
    which reads as a broken environment rather than an unsupported language,
    and cost three agents a session's worth of debugging.
    """

    toolchain = "none"

    def __init__(self, supported):
        self._supported = tuple(supported)

    def available(self, repo_root):
        """Always -- this is the fallback, never a detection result."""
        return True

    def already_red(self, repo_root):
        raise BaselineRunFailedError(
            f"no supported test toolchain detected in {repo_root}, so the "
            "clean-run baseline could not be recorded: the gate knows how to "
            f"run {', '.join(self._supported)}. Pass --suite-runner to name "
            "one explicitly if this repo's markers are unusual."
        )


def _read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _run(argv, repo_root, toolchain):
    """Launch a suite, returning its exit code, bounded like every other
    subprocess the gate starts.

    A timeout is a baseline that did not complete, so it takes the same route
    to the report as any other broken baseline: the audited repo's suite is
    arbitrary code, and one test blocking on a socket would otherwise hang the
    gate inside a scratch workspace still registered as a worktree against the
    operator's repo.
    """
    try:
        result = subprocess.run(
            argv,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=SUITE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise BaselineRunFailedError(
            f"the {toolchain} suite did not finish within "
            f"{SUITE_TIMEOUT_SECONDS}s in {repo_root} while recording the "
            "clean-run baseline, so the baseline did not complete"
        ) from exc
    except OSError as exc:
        raise BaselineRunFailedError(
            f"could not launch the {toolchain} suite in {repo_root} while "
            f"recording the clean-run baseline: {exc}"
        ) from exc
    if result.returncode not in PASS_OR_FAIL:
        raise BaselineRunFailedError(
            f"the {toolchain} suite exited {result.returncode} in {repo_root} "
            "while recording the clean-run baseline -- this is not a normal "
            "pass/fail exit, so the baseline did not complete: "
            f"{result.stderr.strip() or result.stdout.strip()!r}"
        )
    return result.returncode


def _gradle_results(repo_root):
    """Gradle's JUnit XML, from every module of a multi-project build.

    Matched anywhere beneath the root rather than only at it, for the reason
    the pitest backend discovered: in a multi-project build the results land in
    `<module>/build/test-results/`, and anchoring at the root found nothing at
    all -- the default shape of a real Java repository.
    """
    return tuple(sorted(Path(repo_root).glob("**/build/test-results/**/TEST-*.xml")))


def _maven_results(repo_root):
    """Surefire's unit-test reports AND Failsafe's integration ones.

    Both, because both are part of the suite whose green this gate is checking;
    reading only Surefire understates what was already red.
    """
    root = Path(repo_root)
    return tuple(
        sorted(
            list(root.glob("**/target/surefire-reports/TEST-*.xml"))
            + list(root.glob("**/target/failsafe-reports/TEST-*.xml"))
        )
    )


def gradle_suite_runner():
    return JUnitXmlSuiteRunner(
        toolchain="gradle",
        manifests=(
            "build.gradle",
            "build.gradle.kts",
            "settings.gradle",
            "settings.gradle.kts",
        ),
        wrapper="gradlew",
        bare="gradle",
        # `--console=plain` for the same reason the pitest backend passes it:
        # the rich console writes ANSI control sequences into captured output.
        #
        # `--rerun-tasks` is not optional here. `--scope working-tree` copies the
        # operator's `build/` into the scratch workspace verbatim, so Gradle's
        # up-to-date check reported `:test UP-TO-DATE`, exited 0 and rewrote
        # nothing -- and the freshness policy then correctly found no results this
        # run had written and raised, blaming stale results rather than the
        # incremental build. A permanently failing gate on any Gradle repo with a
        # populated `build/`. Maven is unaffected because Surefire always re-forks.
        task_argv=("--console=plain", "--rerun-tasks", "test"),
        locate_results=_gradle_results,
    )


def maven_suite_runner():
    return JUnitXmlSuiteRunner(
        toolchain="maven",
        manifests=("pom.xml",),
        wrapper="mvnw",
        bare="mvn",
        # `-B` (batch mode) for non-interactive, log-friendly output; `test` is
        # the phase, not `verify`, so the baseline costs what the suite costs
        # and not what a full package does.
        task_argv=("-B", "test"),
        locate_results=_maven_results,
    )


def default_suite_runners():
    """The runners resolution walks, most specific marker first.

    THIS ORDER IS THE PRECEDENCE RULE, because `resolve_suite_runner` takes the
    first available one. Node is last deliberately: a `package.json` is routine
    in a JVM or Python repo that builds frontend assets, and `npm test` there
    runs the wrong suite or none at all, so a build manifest outranks it.

    Adding a stack is a runner plus one entry here -- the gate itself does not
    change, and neither does anything that already works.
    """
    return (
        PytestSuiteRunner(),
        gradle_suite_runner(),
        maven_suite_runner(),
        NodeSuiteRunner(),
    )


def resolve_suite_runner(repo_root, runners=None):
    """The runner this repo's markers imply; never `None`.

    An unrecognised repo gets `UnsupportedToolchain`, which fails with a stated
    cause when asked to run. Returning a null object rather than `None` keeps
    the decision polymorphic: the caller injects whatever comes back and has no
    "did detection work?" branch to get wrong.
    """
    candidates = default_suite_runners() if runners is None else tuple(runners)
    for runner in candidates:
        if runner.available(repo_root):
            return runner
    return UnsupportedToolchain(
        runner.toolchain for runner in candidates if runner.toolchain != "none"
    )


def suite_runner_named(toolchain, runners=None):
    """The runner an operator asked for by name, or `None` if there is no such
    runner.

    The escape hatch for a polyglot repo whose markers point at the wrong
    suite. `None` rather than a fallback, so a typo is rejected at the CLI
    instead of silently running a suite the operator did not name.
    """
    candidates = default_suite_runners() if runners is None else tuple(runners)
    for runner in candidates:
        if runner.toolchain == toolchain:
            return runner
    return None


SUPPORTED_TOOLCHAINS = tuple(runner.toolchain for runner in default_suite_runners())
