"""The clean-run baseline, once the audited repo is not a Python one.

The backends were generalised across languages; the baseline underneath them
was not, so it ran `uv run pytest` whatever the repo was. On a Gradle or Maven
project that collects nothing and exits 5 -- outside the (0, 1) pass/fail guard
-- so the baseline raised, the gate returned exit 2, and every refactor and
deletion depending on it was left unverifiable. Exit 2 was correct; it was also
guaranteed, which is what made it useless as a signal (#155).

These tests pin the seam that fixes it: which suite runner a repo resolves to,
what each one runs, and -- the part that matters most -- that a runner which
cannot name the tests that were already red says so instead of returning an
empty baseline that reads as clean.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import mutation_gate
import mutation_gate_baseline
import mutation_gate_toolchain
from mutation_gate import BaselineRunFailedError
from mutation_gate_baseline import (
    default_suite_runners,
    resolve_suite_runner,
    suite_runner_named,
)


def _completed(argv, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        argv, returncode=returncode, stdout=stdout, stderr=stderr
    )


def _capture_invocation(monkeypatch, returncode=0, stdout="", stderr="", writes=None):
    """Record the argv a runner launches, without launching anything.

    `writes` is what the build tool would have done: a callable run *during*
    the fake invocation, so results it produces are new to the freshness
    snapshot the runner took beforehand. Tests that want a STALE report write
    it outside this hook instead -- which is exactly the difference the
    freshness policy exists to see.
    """
    captured = {}

    def fake_run(argv, cwd, capture_output, text, timeout):
        captured["argv"] = list(argv)
        captured["cwd"] = cwd
        captured["timeout"] = timeout
        if writes is not None:
            writes()
        return _completed(argv, returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(mutation_gate_baseline.subprocess, "run", fake_run)
    return captured


def _git_repo_at(path):
    """A real repository, because `changed_paths` and the scratch workspace
    both shell out to git and an empty directory has no HEAD to worktree."""
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    # An inert seed file: git has nothing to commit in an empty directory, and
    # a repo with no commit has no HEAD for the scratch workspace to worktree.
    (Path(path) / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "seed",
        ],
        check=True,
    )
    return path


def _write_junit_xml(destination, class_name, passing=(), failing=(), erroring=()):
    """A JUnit XML result file in the shape Gradle and Surefire both write."""
    cases = []
    for test_name in passing:
        cases.append(f'<testcase classname="{class_name}" name="{test_name}"/>')
    for test_name in failing:
        cases.append(
            f'<testcase classname="{class_name}" name="{test_name}">'
            '<failure message="expected true">boom</failure>'
            "</testcase>"
        )
    for test_name in erroring:
        cases.append(
            f'<testcase classname="{class_name}" name="{test_name}">'
            '<error message="no bean">kaput</error>'
            "</testcase>"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<testsuite name="{class_name}">{"".join(cases)}</testsuite>',
        encoding="utf-8",
    )
    return destination


def _gradle_repo(tmp_path):
    (tmp_path / "build.gradle").write_text("plugins { id 'java' }\n", encoding="utf-8")
    return tmp_path


def _maven_repo(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    return tmp_path


def _python_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "-q"\n', encoding="utf-8"
    )
    return tmp_path


def _node_repo(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "vitest run"}}\n', encoding="utf-8"
    )
    return tmp_path


class TestResolution:
    """Which runner a repo gets. The defect in #155 is entirely here: every
    repo got the pytest one."""

    def test_a_gradle_repo_resolves_the_gradle_runner(self, tmp_path):
        assert resolve_suite_runner(_gradle_repo(tmp_path)).toolchain == "gradle"

    def test_a_maven_repo_resolves_the_maven_runner(self, tmp_path):
        assert resolve_suite_runner(_maven_repo(tmp_path)).toolchain == "maven"

    def test_a_python_repo_resolves_the_pytest_runner(self, tmp_path):
        assert resolve_suite_runner(_python_repo(tmp_path)).toolchain == "pytest"

    def test_a_node_repo_resolves_the_node_runner(self, tmp_path):
        assert resolve_suite_runner(_node_repo(tmp_path)).toolchain == "node"

    def test_a_bare_conftest_is_enough_to_resolve_pytest(self, tmp_path):
        """A Python repo with no pyproject at all still has a suite to run."""
        (tmp_path / "conftest.py").write_text("", encoding="utf-8")

        assert resolve_suite_runner(tmp_path).toolchain == "pytest"

    def test_a_pyproject_with_no_pytest_in_it_does_not_resolve_pytest(self, tmp_path):
        """`pyproject.toml` alone says "Python packaging", not "pytest suite".
        Resolving on its presence would put us back to running `uv run pytest`
        at a repo that never had a pytest suite -- #155's own failure."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "thing"\n', encoding="utf-8"
        )

        assert resolve_suite_runner(tmp_path).toolchain == "none"

    def test_a_jvm_repo_carrying_frontend_tooling_still_resolves_its_build_tool(
        self, tmp_path
    ):
        """A `package.json` for frontend assets is routine in a Java repo, and
        `npm test` there runs the wrong suite (or none). Build manifests are
        the more specific marker, so they win."""
        _node_repo(_gradle_repo(tmp_path))

        assert resolve_suite_runner(tmp_path).toolchain == "gradle"

    def test_a_package_json_with_no_test_script_does_not_resolve_node(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"scripts": {"build": "tsc"}}\n', encoding="utf-8"
        )

        assert resolve_suite_runner(tmp_path).toolchain == "none"

    def test_an_explicit_choice_overrides_detection(self, tmp_path):
        """The escape hatch for a polyglot repo whose markers point at the
        wrong suite. Detection is a default, not a verdict."""
        runner = suite_runner_named("maven")

        assert runner is not None and runner.toolchain == "maven"

    def test_an_unknown_explicit_choice_is_rejected_rather_than_guessed(self):
        assert suite_runner_named("cargo") is None


class TestUnsupportedToolchain:
    """What a repo resolves to when nothing matches. #155's mitigation 1: the
    exit 2 has to name the real cause."""

    def test_an_unrecognised_repo_resolves_a_runner_rather_than_nothing(self, tmp_path):
        """A null object, so the caller has no branch to forget: the failure
        travels the same `_record_baseline` path every other runner does."""
        assert resolve_suite_runner(tmp_path).toolchain == "none"

    def test_it_names_the_real_cause_and_not_a_pytest_exit_code(self, tmp_path):
        runner = resolve_suite_runner(tmp_path)

        with pytest.raises(BaselineRunFailedError) as raised:
            runner.already_red(tmp_path)

        message = str(raised.value)
        assert "no supported test toolchain" in message.lower()
        # The old message read as a broken environment rather than an
        # unsupported language, which is what sent three agents debugging uv.
        assert "exited 5" not in message

    def test_it_lists_the_toolchains_that_would_have_worked(self, tmp_path):
        message = ""
        try:
            resolve_suite_runner(tmp_path).already_red(tmp_path)
        except BaselineRunFailedError as exc:
            message = str(exc)

        for toolchain in ("pytest", "gradle", "maven", "node"):
            assert toolchain in message


class TestPytestRunner:
    """Unchanged behaviour, now reached by resolution rather than by default."""

    def test_it_still_runs_uv_run_pytest(self, tmp_path, monkeypatch):
        captured = {}

        def fake_run(argv, cwd, capture_output, text, timeout):
            captured["argv"] = list(argv)
            return _completed(argv, stdout="")

        monkeypatch.setattr(mutation_gate.subprocess, "run", fake_run)

        resolve_suite_runner(_python_repo(tmp_path)).already_red(tmp_path)

        assert captured["argv"][:3] == ["uv", "run", "pytest"]

    def test_it_reports_the_node_ids_pytest_named_as_red(self, tmp_path, monkeypatch):
        def fake_run(argv, cwd, capture_output, text, timeout):
            return _completed(
                argv,
                returncode=1,
                stdout="FAILED tests/test_a.py::test_flaky - AssertionError\n",
            )

        monkeypatch.setattr(mutation_gate.subprocess, "run", fake_run)

        already_red = resolve_suite_runner(_python_repo(tmp_path)).already_red(tmp_path)

        assert already_red == ("tests/test_a.py::test_flaky",)


class TestGradleRunner:
    @staticmethod
    def _repo_with_wrapper(tmp_path):
        repo_root = _gradle_repo(tmp_path)
        (repo_root / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
        return repo_root

    @staticmethod
    def _results_path(repo_root, class_name="a.FooTest", module=None):
        base = repo_root if module is None else repo_root / module
        return base / "build" / "test-results" / "test" / f"TEST-{class_name}.xml"

    def test_it_prefers_the_wrapper_over_the_ambient_gradle(
        self, tmp_path, monkeypatch
    ):
        """The wrapper pins the build-tool version the way a lockfile pins
        dependencies -- the same reason the pitest backend prefers it."""
        repo_root = self._repo_with_wrapper(tmp_path)
        results = self._results_path(repo_root)
        captured = _capture_invocation(
            monkeypatch,
            writes=lambda: _write_junit_xml(
                results, "a.FooTest", passing=("shouldWork",)
            ),
        )

        resolve_suite_runner(repo_root).already_red(repo_root)

        assert captured["argv"][0] == str(repo_root / "gradlew")
        assert "test" in captured["argv"]

    def test_it_is_bounded_like_every_other_subprocess_the_gate_starts(
        self, tmp_path, monkeypatch
    ):
        repo_root = self._repo_with_wrapper(tmp_path)
        results = self._results_path(repo_root)
        captured = _capture_invocation(
            monkeypatch,
            writes=lambda: _write_junit_xml(
                results, "a.FooTest", passing=("shouldWork",)
            ),
        )

        resolve_suite_runner(repo_root).already_red(repo_root)

        assert captured["timeout"] == mutation_gate.SUITE_TIMEOUT_SECONDS

    def test_it_reads_red_tests_out_of_the_junit_xml(self, tmp_path, monkeypatch):
        repo_root = self._repo_with_wrapper(tmp_path)
        results = self._results_path(repo_root)
        _capture_invocation(
            monkeypatch,
            returncode=1,
            writes=lambda: _write_junit_xml(
                results,
                "a.FooTest",
                passing=("shouldWork",),
                failing=("shouldFail",),
                erroring=("shouldError",),
            ),
        )

        already_red = resolve_suite_runner(repo_root).already_red(repo_root)

        # Errors count as red for the same reason `-rfE` does on the pytest
        # side: a test that never ran is not a test that passed.
        assert set(already_red) == {"a.FooTest.shouldFail", "a.FooTest.shouldError"}
        assert "a.FooTest.shouldWork" not in already_red

    def test_it_collects_every_module_of_a_multi_project_build(
        self, tmp_path, monkeypatch
    ):
        """Anchoring at the root found nothing at all in a real multi-project
        repo -- the same discovery mistake the pitest backend had to fix."""
        repo_root = self._repo_with_wrapper(tmp_path)

        def write_both_modules():
            for module in ("billing", "shipping"):
                _write_junit_xml(
                    self._results_path(repo_root, f"a.{module}.Test", module=module),
                    f"a.{module}.Test",
                    failing=("shouldFail",),
                )

        _capture_invocation(monkeypatch, returncode=1, writes=write_both_modules)

        already_red = resolve_suite_runner(repo_root).already_red(repo_root)

        assert set(already_red) == {
            "a.billing.Test.shouldFail",
            "a.shipping.Test.shouldFail",
        }

    def test_a_stale_result_file_this_run_did_not_write_is_not_read(
        self, tmp_path, monkeypatch
    ):
        """`--scope working-tree` copies the operator's `build/` into the
        workspace, so a previous run's results are there by construction. A run
        that dies before writing must not inherit them -- note this fake writes
        nothing, which is precisely the case."""
        repo_root = self._repo_with_wrapper(tmp_path)
        _write_junit_xml(
            self._results_path(repo_root, "a.StaleTest"),
            "a.StaleTest",
            failing=("shouldFail",),
        )
        _capture_invocation(monkeypatch, returncode=1)

        with pytest.raises(BaselineRunFailedError) as raised:
            resolve_suite_runner(repo_root).already_red(repo_root)

        assert "no test results" in str(raised.value).lower()

    def test_a_non_pass_fail_exit_code_raises_rather_than_reading_as_clean(
        self, tmp_path, monkeypatch
    ):
        """Anything outside (0, 1) means the run itself broke -- an OOM kill, a
        tool that was not there -- exactly as on the pytest side."""
        repo_root = self._repo_with_wrapper(tmp_path)
        _capture_invocation(monkeypatch, returncode=137, stderr="killed")

        with pytest.raises(BaselineRunFailedError) as raised:
            resolve_suite_runner(repo_root).already_red(repo_root)

        assert "137" in str(raised.value)

    def test_a_red_suite_that_named_no_failing_test_raises(self, tmp_path, monkeypatch):
        """The honesty rule for every runner: the build reported failures but
        the results name none, so this baseline cannot tell a phantom kill from
        a real one. Returning () would have said "clean"."""
        repo_root = self._repo_with_wrapper(tmp_path)
        results = self._results_path(repo_root)
        _capture_invocation(
            monkeypatch,
            returncode=1,
            writes=lambda: _write_junit_xml(
                results, "a.FooTest", passing=("shouldWork",)
            ),
        )

        with pytest.raises(BaselineRunFailedError) as raised:
            resolve_suite_runner(repo_root).already_red(repo_root)

        assert "reported failures" in str(raised.value).lower()

    def test_a_green_suite_is_an_empty_baseline_not_an_error(
        self, tmp_path, monkeypatch
    ):
        repo_root = self._repo_with_wrapper(tmp_path)
        results = self._results_path(repo_root)
        _capture_invocation(
            monkeypatch,
            returncode=0,
            writes=lambda: _write_junit_xml(
                results, "a.FooTest", passing=("shouldWork",)
            ),
        )

        assert resolve_suite_runner(repo_root).already_red(repo_root) == ()

    def test_a_missing_build_tool_raises_rather_than_returning_a_clean_baseline(
        self, tmp_path, monkeypatch
    ):
        """No wrapper, and no `gradle` on PATH: nothing ran, so there is no
        baseline -- not an empty one."""
        repo_root = _gradle_repo(tmp_path)
        monkeypatch.setattr(mutation_gate_toolchain.shutil, "which", lambda name: None)

        with pytest.raises(BaselineRunFailedError) as raised:
            resolve_suite_runner(repo_root).already_red(repo_root)

        assert "gradle" in str(raised.value).lower()

    def test_a_timeout_is_a_baseline_that_did_not_complete(self, tmp_path, monkeypatch):
        repo_root = self._repo_with_wrapper(tmp_path)

        def fake_run(argv, cwd, capture_output, text, timeout):
            raise subprocess.TimeoutExpired(argv, timeout)

        monkeypatch.setattr(mutation_gate_baseline.subprocess, "run", fake_run)

        with pytest.raises(BaselineRunFailedError) as raised:
            resolve_suite_runner(repo_root).already_red(repo_root)

        assert "did not finish" in str(raised.value).lower()


class TestMavenRunner:
    @staticmethod
    def _repo_with_wrapper(tmp_path):
        repo_root = _maven_repo(tmp_path)
        (repo_root / "mvnw").write_text("#!/bin/sh\n", encoding="utf-8")
        return repo_root

    def test_it_prefers_the_wrapper_and_runs_the_test_phase(
        self, tmp_path, monkeypatch
    ):
        repo_root = self._repo_with_wrapper(tmp_path)
        results = repo_root / "target" / "surefire-reports" / "TEST-a.FooTest.xml"
        captured = _capture_invocation(
            monkeypatch,
            writes=lambda: _write_junit_xml(
                results, "a.FooTest", passing=("shouldWork",)
            ),
        )

        resolve_suite_runner(repo_root).already_red(repo_root)

        assert captured["argv"][0] == str(repo_root / "mvnw")
        assert "test" in captured["argv"]

    def test_it_reads_red_tests_out_of_the_surefire_reports(
        self, tmp_path, monkeypatch
    ):
        repo_root = self._repo_with_wrapper(tmp_path)
        results = repo_root / "target" / "surefire-reports" / "TEST-a.FooTest.xml"
        _capture_invocation(
            monkeypatch,
            returncode=1,
            writes=lambda: _write_junit_xml(
                results, "a.FooTest", failing=("shouldFail",)
            ),
        )

        already_red = resolve_suite_runner(repo_root).already_red(repo_root)

        assert already_red == ("a.FooTest.shouldFail",)

    def test_it_reads_the_failsafe_reports_too(self, tmp_path, monkeypatch):
        """Integration tests are part of the suite whose green this gate is
        checking; leaving them out understates what was already red."""
        repo_root = self._repo_with_wrapper(tmp_path)
        results = repo_root / "target" / "failsafe-reports" / "TEST-a.FooIT.xml"
        _capture_invocation(
            monkeypatch,
            returncode=1,
            writes=lambda: _write_junit_xml(
                results, "a.FooIT", failing=("shouldFail",)
            ),
        )

        already_red = resolve_suite_runner(repo_root).already_red(repo_root)

        assert already_red == ("a.FooIT.shouldFail",)


class TestNodeRunner:
    def test_it_runs_the_repo_s_own_test_script(self, tmp_path, monkeypatch):
        repo_root = _node_repo(tmp_path)
        captured = _capture_invocation(monkeypatch)

        resolve_suite_runner(repo_root).already_red(repo_root)

        assert captured["argv"][:2] == ["npm", "test"]

    def test_a_green_suite_is_an_empty_baseline(self, tmp_path, monkeypatch):
        repo_root = _node_repo(tmp_path)
        _capture_invocation(monkeypatch, returncode=0)

        assert resolve_suite_runner(repo_root).already_red(repo_root) == ()

    def test_a_red_suite_raises_because_it_cannot_name_which_tests(
        self, tmp_path, monkeypatch
    ):
        """`npm test` fans out to whatever runner the repo chose, and its
        console format is not a contract this gate can parse. A red suite it
        cannot enumerate is unusable as a baseline -- and saying so is the
        whole point, because the alternative reads as clean and manufactures
        phantom kills."""
        repo_root = _node_repo(tmp_path)
        _capture_invocation(monkeypatch, returncode=1)

        with pytest.raises(BaselineRunFailedError) as raised:
            resolve_suite_runner(repo_root).already_red(repo_root)

        message = str(raised.value).lower()
        assert "cannot name" in message or "could not name" in message


class TestTheContractEveryRunnerHonours:
    def test_every_registered_runner_answers_the_same_three_questions(self):
        for runner in default_suite_runners():
            assert isinstance(runner.toolchain, str) and runner.toolchain
            assert callable(runner.available)
            assert callable(runner.already_red)

    def test_the_registry_is_ordered_most_specific_marker_first(self):
        """Resolution takes the first available runner, so this order IS the
        precedence rule that keeps a JVM repo's `package.json` from winning."""
        assert [runner.toolchain for runner in default_suite_runners()] == [
            "pytest",
            "gradle",
            "maven",
            "node",
        ]

    def test_no_registered_runner_claims_an_empty_directory(self, tmp_path):
        assert [
            runner.toolchain
            for runner in default_suite_runners()
            if runner.available(tmp_path)
        ] == []


class TestTheGateWiresTheResolvedRunnerIn:
    def test_main_injects_the_runner_the_repo_resolved_to(self, tmp_path, monkeypatch):
        """The defect was here: `main` passed `_pytest_run_suite` whatever the
        repo was, so the polymorphic backends sat on a monomorphic baseline."""
        recorded = {}

        def fake_record_baseline(repo_root, collect_already_red):
            recorded["collect"] = collect_already_red
            return (), ""

        monkeypatch.setattr(mutation_gate, "_record_baseline", fake_record_baseline)
        repo_root = _git_repo_at(_gradle_repo(tmp_path))

        mutation_gate.main(["--repo-root", str(repo_root), "--scope", "full"])

        assert recorded["collect"].__self__.toolchain == "gradle"

    def test_an_explicit_suite_runner_flag_beats_detection(self, tmp_path, monkeypatch):
        recorded = {}

        def fake_record_baseline(repo_root, collect_already_red):
            recorded["collect"] = collect_already_red
            return (), ""

        monkeypatch.setattr(mutation_gate, "_record_baseline", fake_record_baseline)
        repo_root = _git_repo_at(_gradle_repo(tmp_path))

        mutation_gate.main(
            [
                "--repo-root",
                str(repo_root),
                "--scope",
                "full",
                "--suite-runner",
                "maven",
            ]
        )

        assert recorded["collect"].__self__.toolchain == "maven"


class TestTheCliReportsRatherThanCrashes:
    """The gate run the way an agent actually runs it: as a script, through
    `bin/mente-python`, not as an imported module."""

    @staticmethod
    def _run_cli(repo_root, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[1] / "scripts" / "mutation_gate.py"
                ),
                "--repo-root",
                str(repo_root),
                "--scope",
                "full",
                *extra,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

    def test_an_unsupported_repo_exits_2_with_the_cause_in_the_payload(self, tmp_path):
        """Executed as a script this module is `__main__` while every sibling
        imports `mutation_gate`, so the interpreter holds two copies of every
        class defined there -- and a `BaselineRunFailedError` raised by a suite
        runner was a different class from the one `_record_baseline` catches.
        It escaped as a traceback and exit 1 instead of the reportable
        `baseline_error` this gate promises. Only an out-of-process run sees
        it: in-process, the two copies are one."""
        repo_root = _git_repo_at(tmp_path)

        completed = self._run_cli(repo_root)

        assert completed.returncode == 2, completed.stderr
        assert "Traceback" not in completed.stderr
        payload = json.loads(completed.stdout)
        assert "no supported test toolchain" in payload["baseline_error"]
        assert payload["unverified_reasons"]

    def test_an_unknown_suite_runner_is_rejected_by_the_cli(self, tmp_path):
        completed = self._run_cli(_git_repo_at(tmp_path), "--suite-runner", "cargo")

        assert completed.returncode == 2
        assert "invalid choice" in completed.stderr
