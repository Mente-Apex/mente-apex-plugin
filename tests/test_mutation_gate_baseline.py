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


def test_pytest_run_suite_warns_rather_than_silently_reporting_a_clean_baseline_on_a_broken_run(
    tmp_path, monkeypatch
):
    """A collection error or internal pytest crash exits neither 0 nor 1.
    Reading that silently as an empty (all-clean) baseline would let every
    survivor in the run be trusted at face value despite the baseline never
    having actually completed -- the exact silence this feature exists to
    close."""

    def fake_run(argv, cwd, capture_output, text):
        return subprocess.CompletedProcess(
            argv, returncode=4, stdout="", stderr="usage error: bad args"
        )

    monkeypatch.setattr(mutation_gate.subprocess, "run", fake_run)

    with pytest.warns(UserWarning, match="usage error"):
        mutation_gate._pytest_run_suite(tmp_path)
