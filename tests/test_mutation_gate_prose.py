"""The prose backend's three mutation operators.

Where mutmut and Stryker derive a mutant-to-test mapping from coverage, prose
has none, so the test declares its target with @pytest.mark.covers and the
harness mutates exactly that slice. Windowing the wrong region is precisely the
bug class this replaces.
"""

from pathlib import Path

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


DOC_WITH_FENCE = """# Title

## Step 2

Intro line.

```python
# Step 2 is just a comment inside code, not a heading.
print("still inside the fence")
```

Tail line still in Step 2.

## Step 3

Other section.
"""


def test_extract_section_does_not_treat_a_hash_comment_inside_a_fence_as_a_heading():
    section = extract_section(DOC_WITH_FENCE, "Step 2")

    assert "still inside the fence" in section
    assert "Tail line still in Step 2." in section
    assert "Other section" not in section


DOC_FENCE_BEFORE_HEADING = """# Title

```markdown
## Step 2
This is example markdown inside a fence, not the real heading.
```

## Step 2

Real content for step 2.

## Step 3

Other.
"""


def test_extract_section_ignores_a_heading_look_alike_inside_a_fence():
    section = extract_section(DOC_FENCE_BEFORE_HEADING, "Step 2")

    assert "Real content for step 2." in section
    assert "example markdown inside a fence" not in section


def test_invert_operator_does_not_corrupt_words_containing_directive_substrings():
    doc = """# Title

## Step 2

Whenever this happens it is always true, and nevertheless the loop MUST run.

## Step 3

Other.
"""
    mutated = mutate(doc, "Step 2", operator="invert")

    assert "Whenever this happens it is never true" in mutated
    assert "Whealways" not in mutated
    assert "nevertheless" in mutated
    assert "MUST NOT run" in mutated


def test_extract_section_does_not_treat_a_longer_numbered_heading_as_a_match():
    doc = """# Title

## Step 20

Content that belongs to Step 20, not Step 2.
"""
    with pytest.raises(ValueError, match="Step 2"):
        extract_section(doc, "Step 2")


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


def test_a_heading_only_guard_is_killed_by_delete_but_survives_blank_and_invert(
    tmp_path,
):
    from mutation_gate_prose import prose_survivors

    artifact = tmp_path / "doc.md"
    artifact.write_text(DOC, encoding="utf-8")
    declarations = [("tests/test_doc.py::test_heading_only", "doc.md", "Step 2")]

    def run_test(node_id):
        # Green as long as the heading itself is still present — a guard
        # that never actually reads the body content. `blank` and `invert`
        # both leave the heading untouched, so only `delete` should kill it;
        # a predicate falsified by all three (as the original version of
        # this test used) can't tell delete's discrimination from theirs.
        return "## Step 2" in artifact.read_text(encoding="utf-8")

    survivors = prose_survivors(tmp_path, declarations, run_test=run_test)

    assert {s.mutant for s in survivors} == {"blank", "invert"}


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


def test_collect_declarations_reads_the_manifest_pytest_wrote_not_its_stdout():
    """End-to-end: a real `uv run pytest --collect-only` subprocess against
    this very suite. `-q --collect-only` prints pytest's own node-id list and
    a summary line to stdout around whatever the `--covers-manifest=-` hook
    prints, so parsing stdout as JSON always raised `JSONDecodeError` — this
    only proves anything by actually invoking the subprocess and the real
    conftest.py hook, not by mocking either.
    """
    from mutation_gate_prose import collect_declarations

    repo_root = Path(__file__).resolve().parents[1]

    declarations = collect_declarations(repo_root)

    assert (
        "tests/test_mutation_gate_prose.py::"
        "test_the_marker_delivers_the_declared_slice_and_nothing_else",
        "skills/test-quality/SKILL.md",
        "Applying is guarded by two gates",
    ) in declarations


def test_collect_declarations_raises_on_a_genuine_collection_failure(
    tmp_path, monkeypatch
):
    """A nonzero pytest exit is a real defect, not silence-by-design — it
    must not be folded into the same empty-tuple result as "no test declared
    a marker".
    """
    import subprocess

    import mutation_gate_prose

    class _FailedRun:
        returncode = 2
        stdout = ""
        stderr = "collected 0 items / 1 error"

    def fake_run(*args, **kwargs):
        return _FailedRun()

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="collection failed"):
        mutation_gate_prose.collect_declarations(tmp_path)
