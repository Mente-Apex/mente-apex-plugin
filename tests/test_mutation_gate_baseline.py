"""Tests that were already red before any mutant was applied.

A test failing intermittently produces phantom kills: the mutant looks caught,
but the test would have failed anyway. Recording the clean baseline is what
separates "this mutant was killed" from "this test is broken".
"""

import subprocess

import pytest

import mutation_gate
from mutation_gate import Survivor, baseline, run_gate


class FakeBackend:
    stack = "python"
    tool = "mutmut"

    def __init__(self, survivors=()):
        self._survivors = survivors

    def available(self, repo_root):
        return True

    def install_hint(self, repo_root):
        return "uv add --dev mutmut"

    def survivors(self, repo_root, paths):
        return self._survivors


def test_a_baseline_failure_is_carried_into_the_result(tmp_path):
    result = run_gate(
        tmp_path,
        ["a.py"],
        [FakeBackend()],
        baseline_failures=("tests/test_a.py::test_flaky",),
    )

    assert result.baseline_failures == ("tests/test_a.py::test_flaky",)


def test_a_survivor_whose_only_test_was_already_red_is_marked_inconclusive(tmp_path):
    survivor = Survivor(
        artifact="a.py",
        location="a.py:1",
        mutant="x -> y",
        associated_tests=("tests/test_a.py::test_flaky",),
        backend="mutmut",
        granularity="line",
    )

    result = run_gate(
        tmp_path,
        ["a.py"],
        [FakeBackend(survivors=(survivor,))],
        baseline_failures=("tests/test_a.py::test_flaky",),
    )

    assert result.survivors[0].status == "unreliable_baseline"


def test_a_clean_baseline_leaves_survivors_alone(tmp_path):
    survivor = Survivor(
        artifact="a.py",
        location="a.py:1",
        mutant="x -> y",
        associated_tests=("tests/test_a.py::test_sound",),
        backend="mutmut",
        granularity="line",
    )

    result = run_gate(tmp_path, ["a.py"], [FakeBackend(survivors=(survivor,))])

    assert result.survivors[0].status == "survived"
    assert result.baseline_failures == ()


def test_a_survivor_covered_by_one_clean_and_one_flaky_test_stays_a_real_survivor(
    tmp_path,
):
    """Only some of a survivor's covering tests were already red. The
    quantifier matters here: `any` would silence real signal from the clean
    test just because a sibling test happens to be flaky, so the gate must use
    `all` -- unreliable only when every covering test was already broken."""
    survivor = Survivor(
        artifact="a.py",
        location="a.py:1",
        mutant="x -> y",
        associated_tests=(
            "tests/test_a.py::test_flaky",
            "tests/test_a.py::test_sound",
        ),
        backend="mutmut",
        granularity="line",
    )

    result = run_gate(
        tmp_path,
        ["a.py"],
        [FakeBackend(survivors=(survivor,))],
        baseline_failures=("tests/test_a.py::test_flaky",),
    )

    assert result.survivors[0].status == "survived"


def test_a_survivor_with_no_associated_tests_is_unaffected_by_the_baseline(tmp_path):
    """No test covers this mutant at all, so the baseline has nothing to say
    about it -- it is a real, uncovered survivor either way."""
    survivor = Survivor(
        artifact="a.py",
        location="a.py:1",
        mutant="x -> y",
        associated_tests=(),
        backend="mutmut",
        granularity="line",
    )

    result = run_gate(
        tmp_path,
        ["a.py"],
        [FakeBackend(survivors=(survivor,))],
        baseline_failures=("tests/test_a.py::test_flaky",),
    )

    assert result.survivors[0].status == "survived"


def test_baseline_returns_the_node_ids_a_clean_run_already_reported_failed(tmp_path):
    """`baseline` is the piece the spec needs but the plumbing alone cannot
    provide: without it, `baseline_failures` has no real source and the
    feature is inert on an actual run."""

    def fake_run_suite(repo_root):
        assert repo_root == tmp_path
        return (
            "F.F\n"
            "=========================== short test summary info ===========================\n"
            "FAILED tests/test_a.py::test_flaky - AssertionError: boom\n"
            "FAILED tests/test_b.py::test_also_flaky\n"
        )

    result = baseline(tmp_path, fake_run_suite)

    assert result == (
        "tests/test_a.py::test_flaky",
        "tests/test_b.py::test_also_flaky",
    )


def test_baseline_of_a_fully_clean_run_is_empty(tmp_path):
    def fake_run_suite(repo_root):
        return "..... [100%]\n"

    assert baseline(tmp_path, fake_run_suite) == ()


def test_pytest_run_suite_invokes_uv_run_pytest(tmp_path, monkeypatch):
    """Never a bare `pytest` or system interpreter -- this repo's Python
    toolchain is uv-managed."""
    captured = {}

    def fake_run(argv, cwd, capture_output, text):
        captured["argv"] = argv
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(argv, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(mutation_gate.subprocess, "run", fake_run)

    output = mutation_gate._pytest_run_suite(tmp_path)

    assert captured["argv"][:3] == ["uv", "run", "pytest"]
    assert captured["cwd"] == tmp_path
    assert output == "ok\n"


def test_pytest_run_suite_raises_rather_than_silently_reporting_a_clean_baseline_on_a_broken_run(
    tmp_path, monkeypatch
):
    """A collection error or internal pytest crash exits neither 0 nor 1. A
    non-{0,1} exit means the baseline produced NO DATA AT ALL -- unlike a
    missing tool (an honest partial answer), a baseline that never ran must
    not be laundered into "no survivors were unreliable" for the rest of the
    report. Reading it as an empty (all-clean) baseline -- even with a
    warning attached -- lets every survivor in the run be trusted at face
    value in the rendered report, where nothing captures Python warnings.
    Raising instead forces the caller to make that failure a first-class,
    operator-visible part of the result."""

    def fake_run(argv, cwd, capture_output, text):
        return subprocess.CompletedProcess(
            argv, returncode=4, stdout="", stderr="usage error: bad args"
        )

    monkeypatch.setattr(mutation_gate.subprocess, "run", fake_run)

    with pytest.raises(mutation_gate.BaselineRunFailedError, match="usage error"):
        mutation_gate._pytest_run_suite(tmp_path)


def test_record_baseline_turns_a_clean_run_into_failures_with_no_error(tmp_path):
    def fake_run_suite(repo_root):
        return "FAILED tests/test_a.py::test_flaky\n"

    failures, error = mutation_gate._record_baseline(tmp_path, fake_run_suite)

    assert failures == ("tests/test_a.py::test_flaky",)
    assert error == ""


def test_record_baseline_turns_a_broken_run_into_an_error_with_no_failures(tmp_path):
    """The reviewer's live reproduction: a repo whose suite hits a collection
    error must surface as an explicit error, not as an empty, falsely-clean
    baseline."""

    def fake_run_suite(repo_root):
        raise mutation_gate.BaselineRunFailedError("collection error: bad_module.py")

    failures, error = mutation_gate._record_baseline(tmp_path, fake_run_suite)

    assert failures == ()
    assert "collection error" in error


def test_a_broken_baseline_reaches_the_rendered_markdown_and_the_json_payload(
    tmp_path,
):
    """End to end through the reviewer's exact concern: a collection error
    (exit 2) during the baseline run must not degrade to a silent warning
    only visible to something that captures Python warnings -- it must show
    up in both operator-facing outputs, distinguishing "the baseline was
    clean" from "the baseline never ran"."""
    from mutation_gate_report import as_report_payload, render_markdown

    def collection_error_run_suite(repo_root):
        raise mutation_gate.BaselineRunFailedError(
            "uv run pytest exited 2 in "
            f"{repo_root}: ERROR collecting tests/test_broken.py"
        )

    baseline_failures, baseline_error = mutation_gate._record_baseline(
        tmp_path, collection_error_run_suite
    )
    survivor = Survivor(
        artifact="a.py",
        location="a.py:1",
        mutant="x -> y",
        associated_tests=("tests/test_a.py::test_sound",),
        backend="mutmut",
        granularity="line",
    )
    result = run_gate(
        tmp_path,
        ["a.py"],
        [FakeBackend(survivors=(survivor,))],
        baseline_failures=baseline_failures,
        baseline_error=baseline_error,
    )

    assert result.baseline_error != ""
    assert result.survivors[0].status == "survived"

    payload = as_report_payload(result, scope="merge-base")
    assert payload["baseline_error"] != ""
    assert "ERROR collecting tests/test_broken.py" in payload["baseline_error"]

    markdown = render_markdown(result, scope="merge-base")
    assert "ERROR collecting tests/test_broken.py" in markdown
    assert (
        "never ran" in markdown
        or "did not run" in markdown
        or "did not complete" in markdown
    )
