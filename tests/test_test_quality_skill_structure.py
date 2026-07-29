"""Structural guards for the test-quality skill's mutation-gate wiring.

Authored prose, not runtime code. Every guard declares the slice it verifies via
@pytest.mark.covers, so the mutation gate can check these guards are not
themselves vacuous — the failure mode that motivated the whole feature.
"""

import pytest


@pytest.mark.covers(
    "skills/test-quality/SKILL.md", section="Applying is guarded by two gates"
)
def test_gate_a_names_the_script_rather_than_a_manual_procedure(covered_slice):
    assert "scripts/mutation_gate.py" in covered_slice
    assert "manual" in covered_slice.lower()


@pytest.mark.covers("skills/test-quality/agents/analyzer.md", section="Mutation sweep")
def test_the_analyzer_sweeps_the_diff_and_stays_read_only(covered_slice):
    assert "merge-base" in covered_slice
    assert "scratch" in covered_slice.lower()
    assert "read-only" in covered_slice.lower()


@pytest.mark.covers("skills/test-quality/agents/analyzer.md", section="Mutation sweep")
def test_the_analyzer_files_survivors_as_rubric_eleven_findings(covered_slice):
    assert "rubric 11" in covered_slice.lower() or "rubric-11" in covered_slice.lower()
    assert "unverifiable by construction" in covered_slice


@pytest.mark.covers("skills/test-quality/agents/implementer.md", section="Gate A")
def test_gate_a_keeps_the_manual_loop_as_the_documented_fallback(covered_slice):
    assert "scripts/mutation_gate.py" in covered_slice
    assert "fallback" in covered_slice.lower()
