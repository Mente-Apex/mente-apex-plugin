"""Both chunk-review lenses must measure before judging, and neither may block."""

from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1] / "skills"
CLEAN_CODE = (SKILLS / "clean-code/SKILL.md").read_text()
SOLID = (SKILLS / "solid/SKILL.md").read_text()


class TestBothLensesMeasure:
    def test_clean_code_names_the_probe(self):
        assert "complexity_probe.py" in CLEAN_CODE

    def test_solid_names_the_probe(self):
        assert "complexity_probe.py" in SOLID

    def test_both_use_the_review_sink(self):
        assert "--sink review" in CLEAN_CODE
        assert "--sink review" in SOLID


class TestNeitherBlocksAHuman:
    def test_clean_code_says_it_never_blocks(self):
        assert "never blocks" in CLEAN_CODE.lower()

    def test_solid_says_it_never_blocks(self):
        assert "never blocks" in SOLID.lower()

    def test_neither_passes_the_gate_flag(self):
        assert "--gate" not in CLEAN_CODE
        assert "--gate" not in SOLID


class TestTheScopeFormsAreDocumented:
    def test_clean_code_documents_the_range_form(self):
        assert ":40-120" in CLEAN_CODE or "start-end" in CLEAN_CODE

    def test_solid_documents_the_range_form(self):
        assert ":40-120" in SOLID or "start-end" in SOLID
