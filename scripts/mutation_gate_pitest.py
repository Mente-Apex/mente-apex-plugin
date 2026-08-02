"""The Java backend: run PIT and read its mutations.xml.

PIT (pitest.org) is the mature mutation engine for the JVM, and it is the
richest of the four backends on location: every mutant carries a class, a
method, a line and the operator that produced it. Where it is *poorer* than
Stryker is test association — PIT names the tests that covered a surviving
mutant only when the build enables `fullMutationMatrix`, so `associated_tests`
is populated from `<succeedingTests>` when present and empty otherwise. That is
the safe direction: `run_gate` downgrades a survivor to `unreliable_baseline`
only when it HAS associated tests, so an empty tuple leaves a real finding
reported as a real finding rather than explaining it away.

Four decisions worth stating, because each differs from the Stryker backend and
each was deliberate.

**The gate never generates PIT's configuration.** Stryker's config is a
standalone `stryker.conf.json` the gate can drop into a scratch workspace; PIT's
lives inside `pom.xml` or `build.gradle`, so generating it means rewriting the
audited repo's own build manifest. Worse, the failure mode is silent: a
generated config missing `pitest-junit5-plugin` runs, finds no tests, and
reports every mutant as `NO_COVERAGE` — which renders identically to a module
that genuinely has no tests. So `available()` requires PIT to be declared
already, and an undeclared repo gets an install hint instead of a run that
would quietly understate its own result.

**A report is only this run's if this run wrote it.** PIT accumulates
timestamped report directories, and `scratch_workspace(dirty=True)` copies the
operator's `target/` and `build/` trees into the workspace — so "the newest
`mutations.xml` on disk" is routinely a report from a previous local run,
belonging to different code. Reading one is indistinguishable from a clean
result. `_report_snapshot` records every report's identity *before* the run and
`_report_written_since` accepts only a path that is new or whose mtime moved,
which is exact and has no clock-granularity hole to widen.

**Scoping is per-toolchain, and Gradle has none.** `targetClasses` takes class
globs, not file paths, so a selection has to be translated through a source
root. Maven accepts `-DtargetClasses` because `pitest-maven` declares it as a
user property. **`gradle-pitest-plugin` has no equivalent** — it implements no
`-P` convention for `targetClasses`, and Gradle ignores unknown `-P` properties
without error, so passing one would silently do nothing while this module
claimed the run was scoped. It is therefore not passed at all, and the widened
scope is reported through `scope_notes`.

**A scope that could not be honoured is reported, not warned.** `mutation_gate`
already establishes that a `warnings.warn` alone is insufficient because nothing
in the rendered report captures Python warnings — which is why baseline failures
got their own field. An unscoped run is the same class of fact: the run
completed and its findings are real, but they cover something other than what
was asked for. That goes to `scope_notes`, never to `run_errors`, which would
wrongly print the "did not complete" banner over trustworthy results.
"""

import shutil
import subprocess
import warnings
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from mutation_gate import Survivor

KILLED_STATUS = "KILLED"

STATUS_MAP = {
    "SURVIVED": "survived",
    "NO_COVERAGE": "no_coverage",
    "TIMED_OUT": "timeout",
    "NON_VIABLE": "non_viable",
    "MEMORY_ERROR": "memory_error",
    "RUN_ERROR": "runtime_error",
}

# PIT joins test names with `|`, not `,` -- `MUTATION_MATRIX_TEST_SEPARATOR` in
# its XMLReportListener. Splitting on a comma is not merely wrong here, it is
# unsafe in principle: JUnit 5 parameterized display names routinely contain
# commas, so a comma split would fabricate test names out of one real one.
TEST_NAME_SEPARATOR = "|"

# Where a JVM project's *mutable* sources live. A path under one of these
# resolves to a class PIT can be pointed at.
MAIN_SOURCE_ROOTS = (
    "src/main/java/",
    "src/main/kotlin/",
    "src/main/scala/",
)

# Paths that are legitimately part of a selection but are never mutation
# targets. Critically this includes test sources: this backend serves the
# /test-quality lens, so a changeset that touches tests is the NORMAL input,
# not an anomaly. Treating a changed test file as "untranslatable" would fire
# the all-or-nothing fallback on almost every real run and silently widen the
# scope of nearly every report.
NON_TARGET_SOURCE_ROOTS = (
    "src/test/java/",
    "src/test/kotlin/",
    "src/test/scala/",
    "src/testFixtures/java/",
    "src/testFixtures/kotlin/",
    "src/it/java/",
)

_SOURCE_SUFFIXES = (".java", ".kt", ".scala")


def _artifact_path(mutated_class, source_file):
    """Rebuild a source-root-relative path from the class and its file.

    PIT records `sourceFile` as a bare basename (`Money.java`) and the package
    only inside `mutatedClass`, so neither field alone locates the file. Nested
    and anonymous classes (`Discount$Tier`, `Discount$1`) all report the outer
    file, so the class name is dropped entirely and only its package is used.

    The result is relative to the source root, not to the repository: PIT's XML
    never records which of `src/main/java` or `src/main/kotlin` a class came
    from, and inventing one would be a path that does not exist.
    """
    package = mutated_class.rsplit(".", 1)[0] if "." in mutated_class else ""
    if not package:
        return source_file
    return f"{package.replace('.', '/')}/{source_file}"


def _covering_tests(mutation):
    """The tests that ran and passed against this mutant, when PIT names them.

    `<succeedingTests>` is only emitted under `fullMutationMatrix`; without it
    PIT reports which test *killed* a mutant but never which tests merely
    covered a surviving one. Absent the element, an empty tuple is the honest
    answer — see the module docstring for why that is the safe direction.
    """
    succeeding = mutation.findtext("succeedingTests", default="").strip()
    if not succeeding:
        return ()
    return tuple(
        name.strip() for name in succeeding.split(TEST_NAME_SEPARATOR) if name.strip()
    )


def survivors_from_report(report_xml):
    """Turn a PIT mutations.xml into Survivors.

    `KILLED` is the only status silently dropped — the clean success case.
    `NO_COVERAGE`, `TIMED_OUT`, `NON_VIABLE`, `MEMORY_ERROR` and `RUN_ERROR`
    each come through under their own status: none is a kill, and folding any
    of them into one would hide, for instance, that a whole module compiled its
    mutants but never ran a test against them. A status this module has never
    seen raises rather than shrinking the survivor list, because silence in a
    survivor reporter is indistinguishable from "the suite is fine".

    A mutation missing `mutatedClass` or `sourceFile` raises for the same
    reason. Defaulting them to `""` produced locations like `":31"` — a finding
    an operator cannot act on, from a report this module had already decided to
    trust. Schema drift is loud here or it is invisible everywhere.
    """
    root = ElementTree.fromstring(report_xml)
    survivors = []
    for mutation in root.findall("mutation"):
        raw_status = mutation.get("status")
        if raw_status == KILLED_STATUS:
            continue
        status = STATUS_MAP.get(raw_status)
        if status is None:
            raise ValueError(
                f"unrecognized PIT mutant status {raw_status!r} for "
                f"{mutation.findtext('mutatedClass')!r}; STATUS_MAP needs updating"
            )
        mutated_class = (mutation.findtext("mutatedClass") or "").strip()
        source_file = (mutation.findtext("sourceFile") or "").strip()
        if not mutated_class or not source_file:
            raise ValueError(
                "PIT mutation is missing mutatedClass or sourceFile "
                f"(class={mutated_class!r}, file={source_file!r}, "
                f"status={raw_status!r}); the report cannot be located and "
                "this module will not invent a path for it"
            )
        line_number = mutation.findtext("lineNumber", default="")
        artifact = _artifact_path(mutated_class, source_file)
        operator = mutation.findtext("mutator", default="").rsplit(".", 1)[-1]
        survivors.append(
            Survivor(
                artifact=artifact,
                location=f"{artifact}:{line_number}",
                mutant=f"{operator} -> {mutation.findtext('description', default='')}",
                associated_tests=_covering_tests(mutation),
                backend="pitest",
                granularity="line",
                status=status,
            )
        )
    return tuple(survivors)


def _class_name_under(normalized, root):
    """`com.example.Money` for a path under `root`, else None."""
    index = normalized.rfind(root)
    if index == -1 or not normalized.endswith(_SOURCE_SUFFIXES):
        return None
    relative = normalized[index + len(root) :]
    return relative.rsplit(".", 1)[0].replace("/", ".")


def target_classes_for(paths):
    """`(class_names, unresolved_paths)` for the selected sources.

    Three outcomes per path, and the middle one is what the previous version
    got wrong:

    - under a **main** source root → contributes a class name;
    - under a **test** (or other known non-target) root → contributes nothing,
      silently and correctly. A changed test file is not an untranslatable
      path, it is a legitimate non-target: PIT mutates production code, and
      this backend serves a lens whose whole subject is the test suite, so
      changed tests are the normal input;
    - anywhere else → **unresolved**, which forces the all-or-nothing fallback.

    Returning `()` for the class names alongside a non-empty `unresolved` is
    the fallback signal. Scoping to only the translatable subset would run PIT
    over fewer classes than the operator selected while the report said nothing
    about the ones dropped — silent truncation, which is the failure this gate
    exists to avoid. `rfind` rather than `find` so a path that repeats a source
    root resolves against the last one, which is the real class root.
    """
    class_names = []
    unresolved = []
    for path in paths:
        normalized = str(path).replace("\\", "/")
        if any(root in normalized for root in NON_TARGET_SOURCE_ROOTS):
            continue
        for root in MAIN_SOURCE_ROOTS:
            class_name = _class_name_under(normalized, root)
            if class_name is not None:
                class_names.append(class_name)
                break
        else:
            unresolved.append(normalized)
    if unresolved:
        return (), tuple(unresolved)
    return tuple(class_names), ()


# Build manifests by toolchain, in the order each toolchain prefers them, with
# the marker that means "this manifest declares PIT". A substring check rather
# than a parse: Maven declares `pitest-maven` in XML while Gradle applies
# `info.solidsoft.pitest` in Kotlin or Groovy, and no one parser reads all
# three. The check only gates whether the gate ATTEMPTS a run, and a false
# positive degrades to a named run error rather than to a wrong result.
_BUILD_FILES = {
    "maven": ("pom.xml",),
    "gradle": ("build.gradle.kts", "build.gradle"),
}

_PITEST_MARKER = {
    "maven": "pitest-maven",
    "gradle": "info.solidsoft.pitest",
}


def _manifest_text(repo_root, tool):
    """The concatenated text of `tool`'s manifests, or '' if it has none."""
    text = []
    for name in _BUILD_FILES[tool]:
        candidate = Path(repo_root) / name
        if candidate.is_file():
            try:
                text.append(candidate.read_text(encoding="utf-8"))
            except OSError:
                continue
    return "\n".join(text)


def _pitest_tool(repo_root):
    """The toolchain whose own manifest declares PIT, or None.

    This — not file-presence order — is what decides which build tool runs.
    A repository carrying both a `pom.xml` and a `build.gradle.kts` is common
    and genuinely ambiguous (a Gradle project keeping a POM for publishing, a
    Maven project mid-migration), and resolving it by a hardcoded precedence
    picked wrong half the time: a Gradle build with pitest applied was read as
    Maven, found no `pitest-maven` in the POM, and reported unavailable.

    Deciding by *which manifest declares PIT* answers the question actually
    being asked. Where both declare it the order below settles it, and that
    residual case is a repository that has configured PIT twice.
    """
    for tool in ("maven", "gradle"):
        if _PITEST_MARKER[tool] in _manifest_text(repo_root, tool):
            return tool
    return None


def _build_tool(repo_root):
    """Which build tool this component uses, or None.

    Prefers whichever declares PIT; falls back to file presence so that
    `_argv` and the scope notes still have an answer for a repository that has
    a build but no PIT (the shape `available()` refuses).
    """
    declared = _pitest_tool(repo_root)
    if declared is not None:
        return declared
    for tool in ("maven", "gradle"):
        if _manifest_text(repo_root, tool):
            return tool
    return None


def _build_file_text(repo_root):
    """The text of whichever manifest `_build_tool` selected."""
    tool = _build_tool(repo_root)
    return "" if tool is None else _manifest_text(repo_root, tool)


def _wrapper_or_bare(repo_root, wrapper, bare):
    """Prefer the repo's build-tool wrapper, exactly as a developer would.

    The wrapper pins the build tool version the way a lockfile pins
    dependencies; running the ambient `mvn`/`gradle` can resolve a different
    version than the project's own CI does, which is how a mutation run comes
    back disagreeing with the suite for reasons that have nothing to do with
    mutants.
    """
    wrapper_path = Path(repo_root) / wrapper
    if wrapper_path.is_file():
        return [str(wrapper_path)]
    if shutil.which(bare):
        return [bare]
    return None


def _argv(repo_root, target_classes):
    """The PIT invocation for whichever build tool this component uses.

    `target_classes` reaches the command line for Maven only. `pitest-maven`
    declares `targetClasses` as a `@Parameter(property = …)`, so `-D` works;
    `gradle-pitest-plugin` declares no such convention, and Gradle accepts an
    unknown `-P` without complaint — so passing one would have looked like
    scoping while doing nothing. The Gradle run is therefore whatever the
    project's own `pitest { }` block declares, and `scope_notes` says so.
    """
    tool = _build_tool(repo_root)
    if tool == "maven":
        argv = _wrapper_or_bare(repo_root, "mvnw", "mvn")
        if argv is None:
            return None
        argv = argv + [
            "-B",
            "test-compile",
            "org.pitest:pitest-maven:mutationCoverage",
            "-DoutputFormats=XML",
            "-DtimestampedReports=false",
        ]
        if target_classes:
            argv.append("-DtargetClasses=" + ",".join(target_classes))
        return argv
    if tool == "gradle":
        argv = _wrapper_or_bare(repo_root, "gradlew", "gradle")
        if argv is None:
            return None
        return argv + ["--console=plain", "pitest"]
    return None


# The report directory names both build tools use, matched anywhere beneath the
# component root rather than only at it: in a Maven reactor or a Gradle
# multi-project build the reports land in `<module>/target/pit-reports` and
# `<module>/build/reports/pitest`, and anchoring at the root found nothing at
# all -- which is the default shape of a real Java repository.
_REPORT_MARKERS = ("pit-reports", "pitest")

_REPORT_NAME = "mutations.xml"


def _report_paths(repo_root):
    """Every PIT report beneath this component, at any module depth."""
    return tuple(
        path
        for path in Path(repo_root).rglob(_REPORT_NAME)
        if any(marker in path.parts for marker in _REPORT_MARKERS)
    )


def _report_snapshot(repo_root):
    """Each existing report's identity, taken BEFORE the run.

    The `(path -> mtime_ns)` map is what lets `_report_written_since` tell a
    report this run produced from one that was already lying there. See the
    module docstring: with `--scope working-tree` the workspace is a copy of
    the operator's tree including `target/`, so pre-existing reports are the
    normal case rather than a corner one.
    """
    snapshot = {}
    for path in _report_paths(repo_root):
        try:
            snapshot[path] = path.stat().st_mtime_ns
        except OSError:
            continue
    return snapshot


def _report_written_since(repo_root, snapshot):
    """The newest report this run actually wrote, or None.

    A candidate qualifies only if it is absent from `snapshot` (a new file) or
    its mtime moved (rewritten). Comparing identities rather than comparing a
    timestamp against a captured clock reading is what keeps this exact: there
    is no filesystem-granularity window for a stale report to slip through, and
    no tolerance constant to get wrong.
    """
    written = []
    for path in _report_paths(repo_root):
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            continue
        if snapshot.get(path) != mtime:
            written.append((mtime, path))
    if not written:
        return None
    return max(written)[1]


class PitestBackend:
    """Invokes PIT through the repo's build wrapper and reads its XML report."""

    stack = "java"
    tool = "pitest"

    def __init__(self):
        self._run_errors = ()
        self._scope_notes = ()

    def available(self, repo_root):
        """True only when this backend can ACTUALLY run, not merely be invoked.

        Requires a build file AND a PIT declaration inside it. The gate cannot
        generate PIT's configuration the way it generates Stryker's -- see the
        module docstring -- so an undeclared repo would fail at the run, after
        having been reported as a runnable partition.
        """
        return _pitest_tool(repo_root) is not None

    def install_hint(self, repo_root):
        return (
            "declare PIT in the build: Maven, the org.pitest:pitest-maven plugin "
            "plus org.pitest:pitest-junit5-plugin as a plugin dependency; Gradle, "
            'id("info.solidsoft.pitest") plus pitest("org.pitest:pitest-junit5-plugin"). '
            "The junit5 plugin is not optional on a JUnit 5 suite -- without it PIT "
            "finds no tests and reports every mutant as NO_COVERAGE"
        )

    def run_errors(self, repo_root):
        """Run-level facts from the most recent `survivors()` call.

        Empty unless that call's PIT run never produced a report. Held to the
        same standard as the Stryker and mutmut backends: a tool that did not
        complete is named once here rather than silently read as "no survivors".
        """
        return self._run_errors

    def scope_notes(self, repo_root):
        """What the most recent run actually mutated, when it was not the selection.

        Distinct from `run_errors` on purpose: these runs completed and their
        survivors are real findings. What is not real is the implication that
        they cover the files the operator selected.
        """
        return self._scope_notes

    def survivors(self, repo_root, paths):
        """Run PIT over the workspace and parse the report it wrote.

        A missing report is not folded into "no survivors" -- to anyone reading
        the rendered report that is indistinguishable from a clean run. Neither
        is a *stale* one: the snapshot taken before the run is what makes
        "PIT produced no report" and "PIT left last week's report lying there"
        the same outcome rather than opposite ones.
        `survivors_from_report` still raises on an unrecognised PIT status
        rather than being caught here: that is the gate misunderstanding its
        own data, not a missing tool, and it must fail loudly.
        """
        self._run_errors = ()
        self._scope_notes = ()
        target_classes, unresolved = target_classes_for(paths)
        argv = _argv(repo_root, target_classes)
        if argv is None:
            self._run_errors = (
                f"no usable build tool in {repo_root} -- PIT needs a Maven or "
                "Gradle build, invoked through its wrapper or an installed "
                "mvn/gradle, and neither was reachable",
            )
            warnings.warn(self._run_errors[0], stacklevel=2)
            return ()
        self._scope_notes = self._describe_scope(repo_root, target_classes, unresolved)
        snapshot = _report_snapshot(repo_root)
        run_result = subprocess.run(argv, cwd=repo_root, capture_output=True, text=True)
        report_path = _report_written_since(repo_root, snapshot)
        if report_path is None:
            self._run_errors = (
                f"pitest did not complete in {repo_root} -- the run exited "
                f"{run_result.returncode} and wrote no {_REPORT_NAME} "
                f"(any report already present predates it and was ignored), so "
                f"no result from this partition can be trusted "
                f"(stderr: {run_result.stderr.strip()!r})",
            )
            warnings.warn(self._run_errors[0], stacklevel=2)
            return ()
        return survivors_from_report(report_path.read_text(encoding="utf-8"))

    @staticmethod
    def _describe_scope(repo_root, target_classes, unresolved):
        """Name the gap between what was selected and what PIT will mutate."""
        if _build_tool(repo_root) == "gradle":
            return (
                "pitest (gradle): the selection was NOT used to scope this run. "
                "gradle-pitest-plugin exposes no command-line override for "
                "targetClasses, so PIT mutated whatever the project's own "
                "pitest { } block declares -- which may be wider or narrower "
                "than the files selected",
            )
        if unresolved:
            return (
                "pitest (maven): the selection was NOT used to scope this run. "
                f"{len(unresolved)} selected path(s) could not be resolved to a "
                f"class under {', '.join(MAIN_SOURCE_ROOTS)} "
                f"(first: {unresolved[0]}), and scoping to only the resolvable "
                "subset would have dropped the rest without saying so, so PIT "
                "mutated the project's own declared targetClasses instead",
            )
        if not target_classes:
            return (
                "pitest (maven): the selection contained no mutable production "
                "sources (test files are never mutation targets), so PIT "
                "mutated the project's own declared targetClasses",
            )
        return ()
