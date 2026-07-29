"""The prose backend's three mutation operators.

Where mutmut and Stryker derive a mutant-to-test mapping from coverage, prose
has none, so the test declares its target with @pytest.mark.covers and the
harness mutates exactly that slice. Windowing the wrong region is precisely the
bug class this replaces.
"""

import pytest

from mutation_gate_prose import extract_section, mutate

DOC = """# Title

Intro text.

## Step 2

The loop MUST run per component.
Do NOT skip a component.

## Step 3

Later content mentioning per component too.
"""


def test_extract_section_stops_at_the_next_same_level_heading():
    section = extract_section(DOC, "Step 2")

    assert "MUST run per component" in section
    assert "Later content" not in section


def test_delete_operator_removes_only_the_declared_slice():
    mutated = mutate(DOC, "Step 2", operator="delete")

    assert "MUST run per component" not in mutated
    assert "Later content mentioning per component too." in mutated


def test_blank_operator_keeps_the_heading_and_drops_the_body():
    mutated = mutate(DOC, "Step 2", operator="blank")

    assert "## Step 2" in mutated
    assert "MUST run per component" not in mutated


def test_invert_operator_flips_directive_polarity_inside_the_slice_only():
    mutated = mutate(DOC, "Step 2", operator="invert")

    assert "MUST NOT run per component" in mutated
    assert "Do skip a component." in mutated
    assert "Later content mentioning per component too." in mutated


def test_an_unknown_heading_is_an_error_not_a_silent_no_op():
    with pytest.raises(ValueError, match="Nonexistent"):
        mutate(DOC, "Nonexistent", operator="delete")


@pytest.mark.covers(
    "skills/test-quality/SKILL.md", section="Applying is guarded by two gates"
)
def test_the_marker_delivers_the_declared_slice_and_nothing_else(covered_slice):
    assert "mutation gate" in covered_slice
    assert "## Guardrails" not in covered_slice


def test_a_guard_that_survives_every_operator_is_reported_as_a_survivor(tmp_path):
    from mutation_gate_prose import prose_survivors

    artifact = tmp_path / "doc.md"
    artifact.write_text(DOC, encoding="utf-8")
    declarations = [("tests/test_doc.py::test_vacuous", "doc.md", "Step 2")]

    survivors = prose_survivors(
        tmp_path, declarations, run_test=lambda node_id: True  # always green
    )

    assert survivors[0].associated_tests == ("tests/test_doc.py::test_vacuous",)
    assert survivors[0].granularity == "section"
    assert {s.mutant for s in survivors} == {"delete", "blank", "invert"}


def test_a_guard_killed_by_the_delete_operator_is_not_reported_for_it(tmp_path):
    from mutation_gate_prose import prose_survivors

    artifact = tmp_path / "doc.md"
    artifact.write_text(DOC, encoding="utf-8")
    declarations = [("tests/test_doc.py::test_sound", "doc.md", "Step 2")]

    def run_test(node_id):
        # Green only while the section body is still present.
        return "MUST run per component" in artifact.read_text(encoding="utf-8")

    survivors = prose_survivors(tmp_path, declarations, run_test=run_test)

    assert "delete" not in {s.mutant for s in survivors}


def test_the_artifact_is_byte_identical_even_when_the_runner_raises(tmp_path):
    from mutation_gate_prose import prose_survivors

    artifact = tmp_path / "doc.md"
    artifact.write_text(DOC, encoding="utf-8")
    before = artifact.read_bytes()

    def exploding_runner(node_id):
        raise RuntimeError("pytest died mid-mutant")

    with pytest.raises(RuntimeError):
        prose_survivors(
            tmp_path,
            [("tests/test_doc.py::test_x", "doc.md", "Step 2")],
            run_test=exploding_runner,
        )

    assert artifact.read_bytes() == before
