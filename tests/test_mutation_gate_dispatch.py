"""Dispatch across a mixed codebase, with fakes standing in for the tools.

Fakes, not real runs: a Python API with a TypeScript frontend is the normal
shape this lens audits, and the suite must prove both backends select and merge
without requiring mutmut or Stryker to be installed on the machine running it.
"""

import pytest

from mutation_gate import GateResult, Survivor, run_gate


class FakeBackend:
    """Stands in for mutmut or Stryker; records what it was asked to mutate."""

    def __init__(self, stack, tool, available=True, survivors=()):
        self.stack = stack
        self.tool = tool
        self._available = available
        self._survivors = survivors
        self.called_with = None

    def available(self, repo_root):
        return self._available

    def install_hint(self, repo_root):
        return f"install {self.tool}"

    def survivors(self, repo_root, paths):
        self.called_with = tuple(paths)
        return self._survivors


def survivor(backend):
    return Survivor(
        artifact="a",
        location="a:1",
        mutant="m",
        associated_tests=("t",),
        backend=backend,
        granularity="line",
    )


def test_a_mixed_repo_runs_both_backends_once_each_and_merges_the_results(tmp_path):
    python = FakeBackend("python", "mutmut", survivors=(survivor("mutmut"),))
    js = FakeBackend("js", "stryker", survivors=(survivor("stryker"),))

    result = run_gate(tmp_path, ["api/money.py", "web/cart.ts"], [python, js])

    assert python.called_with == ("api/money.py",)
    assert js.called_with == ("web/cart.ts",)
    assert {s.backend for s in result.survivors} == {"mutmut", "stryker"}


def test_a_backend_with_an_empty_partition_is_never_invoked(tmp_path):
    js = FakeBackend("js", "stryker")

    run_gate(tmp_path, ["api/money.py"], [FakeBackend("python", "mutmut"), js])

    assert js.called_with is None


def test_a_present_stack_with_an_absent_tool_reports_a_hint_and_continues(tmp_path):
    python = FakeBackend("python", "mutmut", available=False)
    js = FakeBackend("js", "stryker", survivors=(survivor("stryker"),))

    result = run_gate(tmp_path, ["api/money.py", "web/cart.ts"], [python, js])

    assert result.unavailable == (("python", "install mutmut"),)
    assert len(result.survivors) == 1


def test_files_no_backend_claims_are_reported_as_unresolved(tmp_path):
    result = run_gate(tmp_path, ["assets/logo.png"], [FakeBackend("python", "mutmut")])

    assert result.unresolved == ("assets/logo.png",)


def test_the_result_carries_no_score_anywhere(tmp_path):
    result = run_gate(tmp_path, ["api/money.py"], [FakeBackend("python", "mutmut")])

    assert not hasattr(result, "score")
    assert isinstance(result, GateResult)


def test_a_file_in_a_known_partition_with_no_registered_backend_is_unclaimed(
    tmp_path,
):
    """Reproduces the Critical: a python file must not vanish just because
    only a js backend was registered. It is a different case from an
    unrecognised suffix, so it must not land in `unresolved` either — it gets
    its own explicitly-named field so nothing disappears."""
    js = FakeBackend("js", "stryker", survivors=(survivor("stryker"),))

    result = run_gate(tmp_path, ["api/money.py", "web/cart.ts"], [js])

    assert result.unclaimed == ("api/money.py",)
    assert result.unresolved == ()
    assert {s.backend for s in result.survivors} == {"stryker"}


def test_two_backends_registered_for_the_same_stack_are_rejected(tmp_path):
    """Reproduces the Important: silent duplicate-stack concatenation is not
    a decision. Registration is rejected loudly instead."""
    first = FakeBackend("python", "mutmut")
    second = FakeBackend("python", "some-other-tool")

    with pytest.raises(ValueError, match="python"):
        run_gate(tmp_path, ["api/money.py"], [first, second])


def test_a_backend_declaring_a_stack_partition_never_produces_is_rejected(
    tmp_path,
):
    """A backend whose `.stack` does not match any key `partition()` ever
    yields is a misconfiguration, not a stack that is merely empty this run —
    the gate fails loudly instead of silently never running it."""
    ghost = FakeBackend("rust", "some-rust-tool")

    with pytest.raises(ValueError, match="rust"):
        run_gate(tmp_path, ["api/money.py"], [ghost])
