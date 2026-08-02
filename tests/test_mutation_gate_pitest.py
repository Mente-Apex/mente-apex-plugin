# tests/test_mutation_gate_pitest.py
"""Parsing PIT's mutations.xml, deciding when the Java backend can run, and
knowing which report belongs to which run.

PIT resolves a survivor to a class, a method and a line — precision comparable
to Stryker's — but it names the *covering* tests only when the build enables
`fullMutationMatrix`. So `associated_tests` is populated when the report carries
`succeedingTests` and empty otherwise, which is the safe direction: `run_gate`
only downgrades a survivor to `unreliable_baseline` when it HAS associated
tests, so an empty tuple leaves a real finding reported as a real finding.

Fixture provenance: tests/fixtures/pitest-mutations.xml is hand-authored in the
shape PIT emits — element names, status vocabulary, and the `|` test-name
separator taken from PIT's XMLReportListener — covering every status PIT can
produce rather than only the ones a single captured run happened to hit. An
earlier revision of this fixture used `,` as the separator and the test below
duly certified the bug; the separator is now asserted against the constant the
module derives from PIT rather than against the fixture's own shape.
"""

import warnings
from pathlib import Path

import pytest

from mutation_gate_pitest import (
    STATUS_MAP,
    TEST_NAME_SEPARATOR,
    PitestBackend,
    _argv,
    _build_file_text,
    _wrapper_or_bare,
    mutants_in_report,
    survivors_from_report,
    target_classes_for,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"

MAVEN_POM_WITH_PITEST = (
    "<project><build><plugins><plugin>"
    "<groupId>org.pitest</groupId><artifactId>pitest-maven</artifactId>"
    "</plugin></plugins></build></project>"
)


def load_report():
    return (FIXTURES / "pitest-mutations.xml").read_text(encoding="utf-8")


def survivors():
    return survivors_from_report(load_report())


def only(status):
    return [survivor for survivor in survivors() if survivor.status == status]


def maven_repo(tmp_path, with_pitest=True):
    """A repo shaped like one PIT can actually run in."""
    (tmp_path / "pom.xml").write_text(
        MAVEN_POM_WITH_PITEST if with_pitest else "<project/>", encoding="utf-8"
    )
    (tmp_path / "mvnw").write_text("#!/bin/sh\n", encoding="utf-8")
    return tmp_path


class TestReadingTheReport:

    def test_killed_is_the_only_status_dropped(self):
        """The fixture holds eight mutations, exactly one of them KILLED."""
        assert len(survivors()) == 7
        assert "KILLED" not in STATUS_MAP

    def test_a_survivor_carries_a_precise_line_location(self):
        survivor = only("survived")[0]

        assert survivor.location == "com/example/money/Money.java:31"
        assert survivor.granularity == "line"
        assert survivor.backend == "pitest"

    def test_the_artifact_path_is_rebuilt_from_the_mutated_class_package(self):
        """PIT records only a bare sourceFile, so the package supplies the path."""
        assert only("survived")[0].artifact == "com/example/money/Money.java"

    def test_a_nested_class_resolves_to_its_outer_source_file(self):
        nested = [s for s in survivors() if s.artifact.endswith("Discount.java")]

        assert nested[0].artifact == "com/example/pricing/Discount.java"

    def test_a_default_package_class_keeps_the_bare_source_file(self):
        report = (
            '<mutations><mutation detected="false" status="SURVIVED">'
            "<sourceFile>Money.java</sourceFile><mutatedClass>Money</mutatedClass>"
            "<lineNumber>7</lineNumber><mutator>a.b.MathMutator</mutator>"
            "<description>swapped</description></mutation></mutations>"
        )

        assert survivors_from_report(report)[0].artifact == "Money.java"

    def test_the_mutant_names_the_operator_without_its_package(self):
        assert only("survived")[0].mutant == (
            "ConditionalsBoundaryMutator -> changed conditional boundary"
        )


class TestStatusMapping:
    """The mapping itself, not merely that five distinct statuses appear.

    The previous version of this class parametrized on PIT's status and then
    never referenced it, asserting only that each mapped value showed up once —
    which the whole STATUS_MAP could be permuted without breaking.
    """

    @pytest.mark.parametrize(
        "pit_status,expected",
        [
            ("SURVIVED", "survived"),
            ("NO_COVERAGE", "no_coverage"),
            ("TIMED_OUT", "timeout"),
            ("NON_VIABLE", "non_viable"),
            ("MEMORY_ERROR", "memory_error"),
            ("RUN_ERROR", "runtime_error"),
        ],
    )
    def test_each_pit_status_maps_to_its_own_gate_status(self, pit_status, expected):
        assert STATUS_MAP[pit_status] == expected

    @pytest.mark.parametrize(
        "pit_status,expected",
        [
            ("NO_COVERAGE", "no_coverage"),
            ("TIMED_OUT", "timeout"),
            ("NON_VIABLE", "non_viable"),
            ("MEMORY_ERROR", "memory_error"),
            ("RUN_ERROR", "runtime_error"),
        ],
    )
    def test_the_mapping_is_what_the_parsed_report_actually_carries(
        self, pit_status, expected
    ):
        """Ties the fixture's own statuses to the map, so neither drifts alone."""
        located = [survivor for survivor in survivors() if survivor.status == expected]
        assert len(located) == 1, f"{pit_status} should parse to exactly one {expected}"

    def test_an_unrecognized_status_raises_rather_than_shrinking_the_list(self):
        drifted = load_report().replace('status="SURVIVED"', 'status="INVENTED"', 1)

        with pytest.raises(ValueError, match="INVENTED"):
            survivors_from_report(drifted)

    def test_a_mutation_missing_its_class_raises_instead_of_locating_nowhere(self):
        """Defaulting to '' produced locations like ':31' — unactionable."""
        drifted = (
            '<mutations><mutation detected="false" status="SURVIVED">'
            "<sourceFile>Money.java</sourceFile>"
            "<lineNumber>31</lineNumber><mutator>a.b.MathMutator</mutator>"
            "<description>swapped</description></mutation></mutations>"
        )

        with pytest.raises(ValueError, match="mutatedClass or sourceFile"):
            survivors_from_report(drifted)

    def test_a_killed_mutation_needs_no_location_to_be_dropped(self):
        """The KILLED skip precedes validation deliberately — a mutant the
        suite caught needs no path, and raising on one would fail a clean run."""
        report = (
            '<mutations><mutation detected="true" status="KILLED">'
            "<lineNumber>1</lineNumber></mutation></mutations>"
        )

        assert survivors_from_report(report) == ()


class TestAssociatedTests:

    def test_the_separator_is_pits_pipe_not_a_comma(self):
        """JUnit 5 display names contain commas; splitting on one fabricates names."""
        assert TEST_NAME_SEPARATOR == "|"

    def test_succeeding_tests_become_the_covering_tests(self):
        assert only("survived")[0].associated_tests == (
            "com.example.money.MoneyTest.memberOverThresholdGetsTenPercentOff",
            "com.example.money.MoneyTest.vacuousGuardAssertsNothingReal",
        )

    def test_a_comma_bearing_test_name_survives_intact(self):
        """A parameterized display name is one test, not two."""
        report = load_report().replace(
            "com.example.money.MoneyTest.memberOverThresholdGetsTenPercentOff",
            "MoneyTest.rejects [1] a, b",
            1,
        )

        assert survivors_from_report(report)[0].associated_tests[0] == (
            "MoneyTest.rejects [1] a, b"
        )

    def test_absent_succeeding_tests_yield_an_empty_tuple_not_a_guess(self):
        """Without fullMutationMatrix PIT names no covering tests at all."""
        without_matrix = [
            s for s in survivors() if s.artifact.endswith("Discount.java")
        ]

        assert without_matrix[0].associated_tests == ()


class TestScopingPitToTheChangedFiles:

    def test_main_source_paths_become_fully_qualified_class_globs(self):
        classes, unresolved = target_classes_for(
            [
                "src/main/java/com/example/money/Money.java",
                "src/main/kotlin/com/example/pricing/Discount.kt",
            ]
        )

        assert classes == ("com.example.money.Money", "com.example.pricing.Discount")
        assert unresolved == ()

    def test_a_changed_test_file_is_a_non_target_not_an_unresolved_path(self):
        """This backend serves /test-quality — changed tests are the NORMAL input.

        Treating them as untranslatable fired the all-or-nothing fallback on
        almost every real run and silently widened the scope of the report.
        """
        classes, unresolved = target_classes_for(
            [
                "src/main/java/com/example/money/Money.java",
                "src/test/java/com/example/money/MoneyTest.java",
            ]
        )

        assert classes == ("com.example.money.Money",)
        assert unresolved == ()

    def test_a_genuinely_unknown_path_scopes_nothing_and_is_named(self):
        classes, unresolved = target_classes_for(
            ["src/main/java/com/example/money/Money.java", "generated/Odd.java"]
        )

        assert classes == ()
        assert unresolved == ("generated/Odd.java",)

    def test_a_repeated_source_root_resolves_against_the_last_one(self):
        classes, _ = target_classes_for(
            ["src/main/java/com/example/src/main/java/A.java"]
        )

        assert classes == ("A",)

    def test_an_empty_selection_resolves_to_nothing_at_all(self):
        assert target_classes_for([]) == ((), ())


class TestTheCommandLine:
    """`_argv` was entirely untested, which is how the Gradle flag bug got in."""

    def test_maven_scopes_with_a_property_pitest_maven_actually_declares(
        self, tmp_path
    ):
        argv = _argv(maven_repo(tmp_path), ("com.example.Money",))

        assert "-DtargetClasses=com.example.Money" in argv
        assert "-DoutputFormats=XML" in argv
        assert "-DtimestampedReports=false" in argv

    def test_maven_omits_the_scope_flag_when_nothing_resolved(self, tmp_path):
        argv = _argv(maven_repo(tmp_path), ())

        assert not any(item.startswith("-DtargetClasses") for item in argv)

    def test_gradle_never_passes_target_classes(self, tmp_path):
        """gradle-pitest-plugin has no -P convention for it, and Gradle
        swallows an unknown -P without error — so passing one would look like
        scoping while doing nothing at all."""
        (tmp_path / "build.gradle.kts").write_text(
            'id("info.solidsoft.pitest")', encoding="utf-8"
        )
        (tmp_path / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")

        argv = _argv(tmp_path, ("com.example.Money",))

        assert argv[-1] == "pitest"
        assert not any("targetClasses" in item for item in argv)

    def test_the_wrapper_wins_over_an_ambient_build_tool(self, tmp_path):
        (tmp_path / "mvnw").write_text("#!/bin/sh\n", encoding="utf-8")

        assert _wrapper_or_bare(tmp_path, "mvnw", "mvn") == [str(tmp_path / "mvnw")]

    def test_no_wrapper_and_no_installed_tool_is_None(self, tmp_path):
        assert (
            _wrapper_or_bare(tmp_path, "gradlew", "definitely-not-a-real-tool") is None
        )

    def test_a_repo_with_no_build_tool_yields_no_argv(self, tmp_path):
        assert _argv(tmp_path, ()) is None


class TestAvailabilityMeansItCanActuallyRun:
    """A build file alone is not enough — PIT must already be declared.

    Unlike Stryker, the gate cannot generate PIT's configuration: doing so means
    editing the audited repo's pom.xml or build.gradle, and a wrong targetTests
    or a missing pitest-junit5-plugin produces a run that finds no tests and
    reports every mutant as NO_COVERAGE — indistinguishable, in the rendered
    report, from a genuinely untested module.
    """

    def test_a_maven_repo_declaring_pitest_is_available(self, tmp_path):
        assert PitestBackend().available(maven_repo(tmp_path)) is True

    def test_a_maven_repo_without_pitest_is_not_available(self, tmp_path):
        assert (
            PitestBackend().available(maven_repo(tmp_path, with_pitest=False)) is False
        )

    def test_a_gradle_repo_applying_the_pitest_plugin_is_available(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text(
            'plugins { id("info.solidsoft.pitest") version "1.15.0" }',
            encoding="utf-8",
        )

        assert PitestBackend().available(tmp_path) is True

    def test_a_gradle_repo_keeping_a_pom_is_still_read_as_gradle(self, tmp_path):
        """A publishing-only pom.xml used to decide availability from the POM
        and report False despite pitest being applied in the Gradle build."""
        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        (tmp_path / "build.gradle.kts").write_text(
            'id("info.solidsoft.pitest")', encoding="utf-8"
        )

        assert "info.solidsoft.pitest" in _build_file_text(tmp_path)

    def test_an_unreadable_build_file_degrades_rather_than_raising(
        self, tmp_path, monkeypatch
    ):
        maven_repo(tmp_path)
        monkeypatch.setattr(
            Path, "read_text", lambda *a, **k: (_ for _ in ()).throw(OSError("nope"))
        )

        assert _build_file_text(tmp_path) == ""

    def test_a_repo_with_no_build_file_at_all_is_not_available(self, tmp_path):
        assert PitestBackend().available(tmp_path) is False

    def test_the_install_hint_names_both_build_tools(self, tmp_path):
        hint = PitestBackend().install_hint(tmp_path)

        assert "pitest-maven" in hint
        assert "info.solidsoft.pitest" in hint
        assert "junit5" in hint.lower()


class TestWhichReportBelongsToThisRun:
    """The Critical: a stale report must never read as a clean run.

    `scratch_workspace(dirty=True)` copies the operator's `target/` into the
    workspace, so a report from their last local pitest run is the normal case,
    not a corner one — and PIT accumulates timestamped report directories by
    design.
    """

    def write_report(self, repo, relative, body, mtime=None):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        if mtime is not None:
            import os

            os.utime(path, (mtime, mtime))
        return path

    def run_with_failing_build(self, repo, monkeypatch, backend):
        class Completed:
            returncode = 1
            stderr = "BUILD FAILURE"
            stdout = ""

        monkeypatch.setattr(
            "mutation_gate_pitest.subprocess.run", lambda *a, **k: Completed()
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            return backend.survivors(repo, ["src/main/java/com/example/A.java"])

    def test_a_stale_report_is_not_read_as_this_runs_result(
        self, tmp_path, monkeypatch
    ):
        maven_repo(tmp_path)
        self.write_report(
            tmp_path,
            "target/pit-reports/202601010000/mutations.xml",
            '<mutations><mutation detected="true" status="KILLED">'
            "<sourceFile>Old.java</sourceFile>"
            "<mutatedClass>a.Old</mutatedClass><lineNumber>1</lineNumber>"
            "<mutator>x.Y</mutator><description>stale</description>"
            "</mutation></mutations>",
            mtime=1,
        )
        backend = PitestBackend()

        result = self.run_with_failing_build(tmp_path, monkeypatch, backend)

        assert result == ()
        assert len(backend.run_errors(tmp_path)) == 1
        assert "BUILD FAILURE" in backend.run_errors(tmp_path)[0]

    def test_a_missing_report_is_named_not_read_as_a_clean_run(
        self, tmp_path, monkeypatch
    ):
        maven_repo(tmp_path)
        backend = PitestBackend()

        result = self.run_with_failing_build(tmp_path, monkeypatch, backend)

        assert result == ()
        assert "BUILD FAILURE" in backend.run_errors(tmp_path)[0]

    def test_a_report_this_run_rewrote_is_accepted(self, tmp_path, monkeypatch):
        maven_repo(tmp_path)
        stale = self.write_report(
            tmp_path, "target/pit-reports/mutations.xml", "<mutations/>", mtime=1
        )
        backend = PitestBackend()
        fixture = load_report()

        def rewrite(*args, **kwargs):
            stale.write_text(fixture, encoding="utf-8")

            class Completed:
                returncode = 0
                stderr = ""
                stdout = ""

            return Completed()

        monkeypatch.setattr("mutation_gate_pitest.subprocess.run", rewrite)
        result = backend.survivors(tmp_path, ["src/main/java/com/example/A.java"])

        assert len(result) == 7
        assert backend.run_errors(tmp_path) == ()

    def test_a_report_in_a_reactor_module_is_found(self, tmp_path, monkeypatch):
        """Anchoring the search at the component root found nothing in a
        multi-module build, which is the default shape of a real Java repo."""
        maven_repo(tmp_path)
        backend = PitestBackend()
        fixture = load_report()

        def write_module_report(*args, **kwargs):
            self.write_report(
                tmp_path, "billing/target/pit-reports/mutations.xml", fixture
            )

            class Completed:
                returncode = 0
                stderr = ""
                stdout = ""

            return Completed()

        monkeypatch.setattr("mutation_gate_pitest.subprocess.run", write_module_report)
        result = backend.survivors(tmp_path, ["src/main/java/com/example/A.java"])

        assert len(result) == 7

    def test_run_errors_is_cleared_by_a_later_successful_run(
        self, tmp_path, monkeypatch
    ):
        """Stryker and the prose backend both guarantee this; pitest had no test."""
        maven_repo(tmp_path)
        backend = PitestBackend()
        self.run_with_failing_build(tmp_path, monkeypatch, backend)
        assert backend.run_errors(tmp_path) != ()

        fixture = load_report()

        def succeed(*args, **kwargs):
            self.write_report(tmp_path, "target/pit-reports/mutations.xml", fixture)

            class Completed:
                returncode = 0
                stderr = ""
                stdout = ""

            return Completed()

        monkeypatch.setattr("mutation_gate_pitest.subprocess.run", succeed)
        backend.survivors(tmp_path, ["src/main/java/com/example/A.java"])

        assert backend.run_errors(tmp_path) == ()


class TestScopeNotesReachTheReport:
    """A run that completed over a wider scope than asked is a caveat, not an
    error — but it cannot be silent either, since `warnings.warn` reaches
    nothing in the rendered report."""

    def test_gradle_always_reports_that_the_selection_did_not_scope_the_run(
        self, tmp_path, monkeypatch
    ):
        (tmp_path / "build.gradle.kts").write_text(
            'id("info.solidsoft.pitest")', encoding="utf-8"
        )
        (tmp_path / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
        backend = PitestBackend()

        class Completed:
            returncode = 1
            stderr = ""
            stdout = ""

        monkeypatch.setattr(
            "mutation_gate_pitest.subprocess.run", lambda *a, **k: Completed()
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            backend.survivors(tmp_path, ["src/main/java/com/example/A.java"])

        notes = backend.scope_notes(tmp_path)
        assert len(notes) == 1
        assert "targetClasses" in notes[0]

    def test_an_unresolved_path_is_named_in_the_notes(self, tmp_path, monkeypatch):
        maven_repo(tmp_path)
        backend = PitestBackend()

        class Completed:
            returncode = 1
            stderr = ""
            stdout = ""

        monkeypatch.setattr(
            "mutation_gate_pitest.subprocess.run", lambda *a, **k: Completed()
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            backend.survivors(
                tmp_path,
                ["src/main/java/com/example/A.java", "generated/Odd.java"],
            )

        assert "generated/Odd.java" in backend.scope_notes(tmp_path)[0]

    def test_a_cleanly_scoped_maven_run_reports_no_caveat(self, tmp_path, monkeypatch):
        maven_repo(tmp_path)
        backend = PitestBackend()

        class Completed:
            returncode = 1
            stderr = ""
            stdout = ""

        monkeypatch.setattr(
            "mutation_gate_pitest.subprocess.run", lambda *a, **k: Completed()
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            backend.survivors(tmp_path, ["src/main/java/com/example/A.java"])

        assert backend.scope_notes(tmp_path) == ()


class TestEveryReactorModuleReportIsRead:
    """`_report_paths` rglobs precisely because a Maven reactor writes one
    report per module. Taking `max(written)` read whichever module finished
    last and silently discarded every other module's survivors -- a reactor
    where `billing` had survivors and `shipping` finished clean reported clean.
    """

    @staticmethod
    def write_report(root, relative, body):
        path = Path(root) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_survivors_from_both_modules_are_reported(self, tmp_path, monkeypatch):
        maven_repo(tmp_path)
        backend = PitestBackend()
        fixture = load_report()
        clean = '<?xml version="1.0" encoding="UTF-8"?>\n<mutations/>\n'

        def write_two_module_reports(*args, **kwargs):
            # billing first, shipping last: under `max(written)` the clean
            # shipping report won and billing's seven survivors vanished.
            self.write_report(
                tmp_path, "billing/target/pit-reports/mutations.xml", fixture
            )
            self.write_report(
                tmp_path, "shipping/target/pit-reports/mutations.xml", clean
            )

            class Completed:
                returncode = 0
                stderr = ""
                stdout = ""

            return Completed()

        monkeypatch.setattr(
            "mutation_gate_pitest.subprocess.run", write_two_module_reports
        )
        result = backend.survivors(tmp_path, ["src/main/java/com/example/A.java"])

        assert len(result) == 7
        assert backend.run_errors(tmp_path) == ()

    def test_the_mutant_count_sums_across_modules(self, tmp_path, monkeypatch):
        maven_repo(tmp_path)
        backend = PitestBackend()
        fixture = load_report()
        # Distinct classes, so these are genuinely different mutants. Writing
        # the same fixture twice would be one module's mutants seen twice, and
        # deduplication correctly collapses that -- see
        # TestAnAggregatedReportDoesNotDoubleCount.
        other = fixture.replace("com.example", "com.other")

        def write_two_module_reports(*args, **kwargs):
            self.write_report(
                tmp_path, "billing/target/pit-reports/mutations.xml", fixture
            )
            self.write_report(
                tmp_path, "shipping/target/pit-reports/mutations.xml", other
            )

            class Completed:
                returncode = 0
                stderr = ""
                stdout = ""

            return Completed()

        monkeypatch.setattr(
            "mutation_gate_pitest.subprocess.run", write_two_module_reports
        )
        backend.survivors(tmp_path, ["src/main/java/com/example/A.java"])

        one_module = mutants_in_report(load_report())
        assert backend.mutants_executed(tmp_path) == one_module * 2


class TestAnAggregatedReportDoesNotDoubleCount:
    """`_report_paths` matches any `mutations.xml` under a `pit-reports` path
    component. A reactor configured with `pitest-aggregator` writes a root
    report covering the same mutants as the per-module ones, all freshly
    written by the same run -- so summing them counted every mutant twice and
    reported each survivor twice.
    """

    @staticmethod
    def write_report(root, relative, body):
        path = Path(root) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_the_same_mutant_seen_twice_is_reported_once(self, tmp_path, monkeypatch):
        maven_repo(tmp_path)
        backend = PitestBackend()
        fixture = load_report()

        def write_module_and_aggregate(*args, **kwargs):
            self.write_report(
                tmp_path, "billing/target/pit-reports/mutations.xml", fixture
            )
            self.write_report(tmp_path, "target/pit-reports/mutations.xml", fixture)

            class Completed:
                returncode = 0
                stderr = ""
                stdout = ""

            return Completed()

        monkeypatch.setattr(
            "mutation_gate_pitest.subprocess.run", write_module_and_aggregate
        )
        result = backend.survivors(tmp_path, ["src/main/java/com/example/A.java"])

        assert len(result) == 7
        assert backend.mutants_executed(tmp_path) == mutants_in_report(load_report())

    def test_two_genuinely_different_modules_still_add_up(self, tmp_path, monkeypatch):
        """The control: dedup must not collapse distinct mutants."""
        maven_repo(tmp_path)
        backend = PitestBackend()
        fixture = load_report()
        other = fixture.replace("com.example", "com.other")

        def write_two_modules(*args, **kwargs):
            self.write_report(
                tmp_path, "billing/target/pit-reports/mutations.xml", fixture
            )
            self.write_report(
                tmp_path, "shipping/target/pit-reports/mutations.xml", other
            )

            class Completed:
                returncode = 0
                stderr = ""
                stdout = ""

            return Completed()

        monkeypatch.setattr("mutation_gate_pitest.subprocess.run", write_two_modules)
        result = backend.survivors(tmp_path, ["src/main/java/com/example/A.java"])

        assert len(result) == 14
        assert backend.mutants_executed(tmp_path) == mutants_in_report(fixture) * 2
